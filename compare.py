# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: '.py'
#       format_name: 'percent'
#       format_version: '1.3'
#   kernelspec:
#     display_name: 'openmc-activator-cdr'
#     language: 'python'
#     name: 'python3'
#   language_info:
#     codemirror_mode:
#       name: 'ipython'
#       version: 3
#     file_extension: '.py'
#     mimetype: 'text/x-python'
#     name: 'python'
#     nbconvert_exporter: 'python'
#     pygments_lexer: 'ipython3'
#     version: '3.14.4'
# ---

# %% [markdown]
# # Simulate depletion
#
# This notebook process the CoNDERC data that contains both experimental and simulation.
#
# Running this notebook also performs OpenMC depletion simulations for every experiment.
#
# This can take over an hour on a typical laptop but is needed for production of all the results.

# %%
import argparse
import multiprocessing as mp
import random
import shutil

from pathlib import Path

NOTEBOOK_ARGS = None


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Run OpenMC/FISPACT comparisons for CoNDERC benchmark cases.'
    )
    parser.add_argument(
        '--materials',
        nargs='+',
        metavar='MATERIAL',
        help='Only run selected materials, for example: --materials Ag Al',
    )
    parser.add_argument(
        '--experiments',
        nargs='+',
        metavar='EXPERIMENT',
        help='Only run selected experiment names, for example: --experiments 2000exp_5min',
    )
    parser.add_argument(
        '--random-select',
        type=int,
        metavar='N',
        help='Randomly select N material/experiment cases after applying filters.',
    )
    parser.add_argument(
        '--random-seed',
        type=int,
        help='Seed for reproducible --random-select choices.',
    )
    return parser.parse_args(argv)


def flatten_cases(experiments):
    return [
        (material, exp)
        for material in sorted(experiments)
        for exp in sorted(experiments[material])
    ]


def experiments_from_cases(cases):
    selected = {}
    for material, exp in cases:
        selected.setdefault(material, []).append(exp)
    return selected


def select_experiments(experiments, args):
    cases = flatten_cases(experiments)

    if args.materials:
        requested_materials = set(args.materials)
        available_materials = set(experiments)
        missing_materials = sorted(requested_materials - available_materials)
        if missing_materials:
            available = ', '.join(sorted(available_materials))
            missing = ', '.join(missing_materials)
            raise SystemExit(f'Requested material(s) not found: {missing}. Available materials: {available}')
        cases = [(material, exp) for material, exp in cases if material in requested_materials]

    if args.experiments:
        requested_experiments = set(args.experiments)
        filtered_cases = [(material, exp) for material, exp in cases if exp in requested_experiments]
        matched_experiments = {exp for _, exp in filtered_cases}
        missing_experiments = sorted(requested_experiments - matched_experiments)
        if missing_experiments:
            available = ', '.join(sorted({exp for _, exp in cases}))
            missing = ', '.join(missing_experiments)
            raise SystemExit(
                f'Requested experiment(s) not found after material filtering: {missing}. '
                f'Available experiments: {available}'
            )
        cases = filtered_cases

    if args.random_select is not None:
        if args.random_select < 1:
            raise SystemExit('--random-select must be at least 1')
        if args.random_select > len(cases):
            raise SystemExit(
                f'--random-select {args.random_select} requested, but only {len(cases)} case(s) are available'
            )
        rng = random.Random(args.random_seed)
        cases = sorted(rng.sample(cases, args.random_select))

    if not cases:
        raise SystemExit('No benchmark cases selected')

    return experiments_from_cases(cases)


def print_selection_summary(experiments, max_cases_to_print=25):
    cases = flatten_cases(experiments)
    print(f'Selected {len(cases)} benchmark case(s) across {len(experiments)} material(s).')
    for material, exp in cases[:max_cases_to_print]:
        print(f'  - {material} {exp}')
    remaining = len(cases) - max_cases_to_print
    if remaining > 0:
        print(f'  ... {remaining} more case(s)')


args = parse_args(NOTEBOOK_ARGS)

if 'fork' in mp.get_all_start_methods():
    mp.set_start_method('fork', force=True)

import numpy as np
import matplotlib.pyplot as plt

from urllib.request import urlopen, Request
from zipfile import ZipFile

import openmc
import pypact as pp  # needs latest version which can be installed with pip install git+https://github.com/fispact/pypact

OPENMC_LABEL = f'OpenMC {openmc.__version__}'
DECAY_START_INDEX = 1

# allows notebook rendering of plotly plots in the HTML made by jupyter-book
import plotly.graph_objects as go
import plotly.offline as pyo
pyo.init_notebook_mode(connected=True)

from openmc_activator import OpenmcActivator, write_markdown_file, read_experimental_data

# %% [markdown]
# This downloads and extracts the CoNDERC data. This contains the FNS experimental data and FISPACT inputs and outputs.

# %%
# download zip file
conderc_url = 'https://nds.iaea.org/conderc/fusion/files/fns.zip'
p = Request(conderc_url, headers={'User-Agent': 'Mozilla/5.0'})
with urlopen(p) as response, open('fns.zip', 'wb') as out_file:
    shutil.copyfileobj(response, out_file)

# unzip
with ZipFile('fns.zip', 'r') as f:
    f.extractall('.')

# %% [markdown]
# Read all the experiments from unzipped fns folder.

# %%
here = Path('./fns')
assert(here.exists()), 'fns folder does not seem to exist. Run `download_fns_fusion_decay.py` first to download and unzip FNS benchmark files.'
experiments = {}
files = sorted((q for q in here.glob('*') if q.is_dir()), key=lambda q: q.name)
for f in files:
    if '_' in f.name: continue
    l = sorted(f.glob('*fluxes*'), key=lambda q: q.name)
    experiments[f.name] = []
    for name in l:
        x = name.name.replace('_fluxes', '')
        experiments[f.name].append(x)
experiments = select_experiments(experiments, args)
print_selection_summary(experiments)

# %% [markdown]
# Reads the Fispact fluxes file that contains the neutron spectra

# %%
# read flux data
flux_dict = {}
for k,l in experiments.items():
    flux_dict[k] = {}
    for exp in l:
        ff = pp.FluxesFile()
        pp.from_file(ff, here / k / (exp+'_fluxes'))
        assert(len(ff.values) == 709)
        ebins = ff.boundaries
        flux_dict[k][exp] = ff.values

# %% [markdown]
# Plot and example irradiation neutron spectra.
#
# This example plots the neutron spectra used to irradiate silver (Ag) in the 2000 experimental campaign for 5 minutes of irradiation.

# %%
# In this case we plot the first selected experiment spectrum but you could plot others.
example_material, example_exp = flatten_cases(experiments)[0]
plt.stairs(values=flux_dict[example_material][example_exp], edges=np.array(ebins)/1e6)
plt.yscale('log')
plt.xlim(0, 16)
plt.xlabel('Energy [MeV]')
plt.ylabel(r'Flux [n$\cdot$cm$^{-2}\cdot$s$^{-1}$]')
plt.title(f'{example_material} {example_exp}')
plt.show()
plt.close()

# %% [markdown]
# Next we read in the experimental data so that it is in a more accessible form.
# The times, data and uncertainties are read in.

# %%
# TODO consider replacing with pypact
def is_days(input_file):
    lines = open(input_file, 'r').readlines()
    lines = [q for q in lines if 'TIME' in lines]
    day_cnt = 0
    for line in lines:
        if 'DAYS' in line: day_cnt += 1
    if day_cnt == len(lines):
        return True
    elif day_cnt == 0:
        return False
    else:
        raise ValueError('Something is not right')

exp_data_dict = {'time': {}, 'data': {}, 'uncert': {}}
for k,l in experiments.items():
    for k_ in exp_data_dict:
        exp_data_dict[k_][k] = {}
    for exp in l:
        exp_path = here / k / (exp+'.exp')
        exp_path = str(exp_path.absolute())
        input_path = here / k / ('TENDL-2017_' + exp + '.i')
        input_path = str(input_path.absolute())
        mins, vals, uncs = read_experimental_data(exp_path)
        if is_days(input_path):
            exp_data_dict['time'][k][exp] = (np.array(mins) * 60 * 24).tolist()
        else:
            exp_data_dict['time'][k][exp] = mins
        exp_data_dict['data'][k][exp] = vals # could convert to micro watts (np.array(vals) * 1e6).tolist()
        exp_data_dict['uncert'][k][exp] = uncs
        assert(len(mins) == len(vals))

# %% [markdown]
# Now we get the irradiation setup including the flux and timesteps

# %%
def read_irr_setup(filepath):
    ff = pp.InputData()
    pp.from_file(ff, filepath)
    flux_mag_list = [val[1] for val in ff._irradschedule] + [0.0] * len(ff._coolingschedule)
    days_list = np.cumsum([val[0] for val in ff._irradschedule] + ff._coolingschedule)/ (24*60*60)
    return days_list.tolist(), flux_mag_list

def read_mat_setup(filepath):
    ff = pp.InputData()
    pp.from_file(ff, filepath)
    return ff._inventorymass.entries

def read_density(filepath):
    ff = pp.InputData()
    pp.from_file(ff, filepath)
    return ff._density

setup_dict = {'days': {}, 'flux_mag': {}, 'mass': {}, 'density': {}}
for k,l in experiments.items():
    for k_ in setup_dict:
        setup_dict[k_][k] = {}
    for exp in l:
        input_path = here / k / ('TENDL-2017_' + exp + '.i')
        input_path = str(input_path.absolute())
        days, flux_mag = read_irr_setup(input_path)
        mass_dict = {k:v/100 for k,v in read_mat_setup(input_path)}
        setup_dict['days'][k][exp] = days
        setup_dict['flux_mag'][k][exp] = flux_mag
        setup_dict['mass'][k][exp] = mass_dict
        setup_dict['density'][k][exp] = read_density(input_path)
        assert(len(days) == len(flux_mag))
        assert(isinstance(mass_dict, dict))


setup_dict['mg_flux'] = flux_dict
setup_dict['ebins'] = ebins

# %% [markdown]
# Now we can carry out depletion simulations in OpenMC
#
# Set the chain file and cross sections to let OpenMC know where to find the data.
#
# The nuclear data used can have an impact on how closely the results match.
#
# To make this a fair comparison we recommend using the same nuclear data as the original Fispact simulations (Tendl 2017) and the chain file provided within the repository.

# %%
# Setting the cross section path to the location used by the CI.
# If you are running this locally you will have to change this path to your local cross section path.
import os

xs_path = os.getenv('OPENMC_CROSS_SECTIONS')

print(f'Using cross section path: {xs_path}')

openmc.config['cross_sections'] = Path(xs_path)

# %%

# Setting the chain file to the relative path of the chain file included in the repository.
# Also resolving the chain file to the absolute path which is needed till the next release of OpenMC.
openmc.config['chain_file'] = Path('./fns_spectrum.chain.xml').resolve()

# %% [markdown]
# Next we use the experiment descriptions to make OpenMC simulations
#
# The irradiation duration, spectra, flux, material and mass are found from the IAEA Conderc benchmarks and passed to OpenMC functions to perform simulations of the experimental setup.

# %%
openmc_result_dict = {}
all_activation_data = []
element_exp_names = []
for k, l in experiments.items():

    # this loop currently just simulates the all materials in the benchmark suite
    # it can be changed to simulate a single material by commenting the line below.
    # if k != 'Ag': continue
    # or it it can be changed to simulate a two materials by commenting the line below.
    # if k not in ['Ag', 'Al']: continue

    print(f'Running OpenMC for {k} {l}')

    if k not in openmc_result_dict:
        openmc_result_dict[k] = {}
    for exp in l:
        if exp in openmc_result_dict[k]:
            continue
        ccfe_flux = flux_dict[k][exp]
        # ebins is ccfs 709 flux bins
        # low to high
        # create new chain file

        # mass in grams
        mass_dict = setup_dict['mass'][k][exp]
        days_list = setup_dict['days'][k][exp]
        # days are cumulative, so we gotta provide diffs
        days_list = np.append(days_list[0], np.diff(days_list))
        flux_mag_list = setup_dict['flux_mag'][k][exp]

        # make openmc material
        mat = openmc.Material()
        for el, md in mass_dict.items():
            el = el.lower().capitalize()
            mat.add_element(el, md, percent_type='wo')
        mat.set_density('g/cm3', setup_dict['density'][k][exp])
        mat.depletable = True
        mat.temperature = 294
        tot_mass = sum(mass_dict.values())
        mat.volume = tot_mass / mat.density

        activation_data = {
            'materials': mat,
            'multigroup_flux': ccfe_flux,
            'energy': ebins,
            'source_rate': flux_mag_list,
            'timesteps': days_list.tolist()
        }
        element_exp_names.append((k,exp))
        all_activation_data.append(activation_data)

# %%
obj = OpenmcActivator(
    activation_data=all_activation_data,
    timestep_units='d',
    chain_file=openmc.config['chain_file'],
)

all_metric_dict = obj.activate(metric_list=['contact_dose_rate'])

# %%
for entry, (k,exp) in zip(all_metric_dict, element_exp_names):

    openmc_result_dict[k][exp] = entry

# %% [markdown]
# Next we process the Fispact simulations results from the IAEA Conderc benchmarks so that they are ready to plot next to the OpenMC simulation results and the experimental benchmark results.

# %%
def read_fispact_dose_rate_output(filepath):
    result = {
        'time': [],
        'contact_dose_rate': [],
        'uncert': [],
    }
    in_summary = False

    with open(filepath) as f:
        for line in f:
            stripped = line.strip()
            if 'Summary Output' in stripped:
                in_summary = True
                continue
            if not in_summary:
                continue
            if stripped.startswith('0 Mass of material input'):
                break
            if not (stripped.startswith('Irradn') or stripped.startswith('Cooling')):
                continue

            parts = stripped.split()
            if len(parts) < 10:
                raise ValueError(f'Could not parse FISPACT summary row in {filepath}: {stripped}')

            if parts[0] == 'Irradn':
                cooling_time_years = 0.0
            else:
                cooling_time_years = float(parts[3])

            dose_rate = float(parts[7])
            percent_uncert = float(parts[9].rstrip('%'))
            result['time'].append(cooling_time_years * 365.25 * 24 * 60)
            result['contact_dose_rate'].append(dose_rate)
            result['uncert'].append(dose_rate * percent_uncert / 100)

    if not result['time']:
        raise ValueError(f'No FISPACT summary dose-rate rows found in {filepath}')

    return result


fispact_result_dict = {}
for k,l in experiments.items():
    fispact_result_dict[k] = {}
    for exp in l:
        output_path = here / k / f'TENDL-2017_{exp}.out'
        fispact_result_dict[k][exp] = read_fispact_dose_rate_output(output_path.resolve())

# %% [markdown]
# We define some plotting functions that will be used later

# %%
def plot_with_matplotlib(
    fispact_time,
    fispact_results,
    fispact_uncert,
    openmc_time,
    openmc_results,
    material,
    experiment,
):
        plt.plot(
            openmc_time,
            openmc_results,
            label=f'{OPENMC_LABEL} absorbed-air (Gy/h)',
            marker='x',
            alpha=0.5,
            color='red'
        )
        plt.errorbar(
            fispact_time,
            fispact_results,
            fispact_uncert,
            label='FISPACT II gamma dose rate (Sv/h)',
            marker='o',
            alpha=0.5,
            color='blue'
        )

        plt.yscale('log')
        plt.xlabel('Minutes')
        plt.ylabel('Contact dose rate')
        plt.legend()
        plt.grid()
        plt.title(f'{material} {experiment} contact dose rate')
        plt.savefig(Path('docs') / f'{material}_{experiment}.png')
        plt.close()

def plot_with_plotly(
    fispact_time,
    fispact_results,
    fispact_uncert,
    openmc_time,
    openmc_results,
    material,
    experiment,
):
    fig = go.Figure()

    # OpenMC results
    fig.add_trace(go.Scatter(
        x=openmc_time,
        y=openmc_results,
        mode='lines+markers',
        name=f'{OPENMC_LABEL} absorbed-air (Gy/h)',
        marker=dict(symbol='x'),
        line=dict(dash='solid', color='red'),
        opacity=0.7,
    ))

    # FISPACT II results with error bars
    fig.add_trace(go.Scatter(
        x=fispact_time,
        y=fispact_results,
        mode='markers+lines',
        name='FISPACT II gamma dose rate (Sv/h)',
        error_y=dict(
            type='data',
            array=fispact_uncert,
            visible=True
        ),
        line=dict(dash='solid', color='blue'),
        marker=dict(symbol='circle'),
        opacity=0.7
    ))

    fig.update_layout(
        yaxis_type="log",
        xaxis_title="Minutes",
        yaxis_title="Contact dose rate",
        legend=dict(title=None),
        title=f"{material} {experiment} contact dose rate",
        template="plotly_white"
    )
    Path('plotly_files').mkdir(exist_ok=True, parents=True)
    fig.write_html(Path('plotly_files') / f'{material}_{experiment}.html')

# %% [markdown]
# We now have the OpenMC contact dose rate and Fispact gamma dose rate in a convenient form ready for plotting.
#
# The next code block plots the results so that they can be compared.

# %%
for k,l in openmc_result_dict.items():
    for exp in l:
        fispact_time = np.array(fispact_result_dict[k][exp]['time'])
        fispact_uncert = np.array(fispact_result_dict[k][exp]['uncert'])
        fispact_results = np.array(fispact_result_dict[k][exp]['contact_dose_rate'])

        # openmc
        decay_indx = DECAY_START_INDEX
        openmc_time = openmc_result_dict[k][exp]['contact_dose_rate']['meta_time_d']
        t0 = openmc_time[decay_indx]
        openmc_time = np.array(openmc_time[decay_indx:]) - t0
        openmc_time = openmc_time * (60*24) # days to minutes
        openmc_results = openmc_result_dict[k][exp]['contact_dose_rate']['meta_total']
        openmc_results = openmc_results[decay_indx:]

        plot_with_plotly(
            fispact_time,
            fispact_results,
            fispact_uncert,
            openmc_time,
            openmc_results,
            k,
            exp,
        )
        plot_with_matplotlib(
            fispact_time,
            fispact_results,
            fispact_uncert,
            openmc_time,
            openmc_results,
            k,
            exp,
        )
    # uncomment to write markdown files for each material, needed for local rendering of the jupyter book
    write_markdown_file(
        experiment_names=l,
        material_name=k
    )

# %%
import json
with open('openmc_result_dict.json', 'w') as f:
    json.dump(openmc_result_dict, f, indent=2)
with open('exp_data_dict.json', 'w') as f:
    json.dump(exp_data_dict, f, indent=2)
with open('fispact_result_dict.json', 'w') as f:
    json.dump(fispact_result_dict, f, indent=2)

# %%

def mean_absolute_percentage_error(experimental, simulated):
    """
    Calculate Mean Absolute Percentage Error

    Returns the average percentage difference between experimental and simulated values.
    Result is expressed as a decimal.
    """
    if len(experimental) != len(simulated):
        print(experimental)
        print(simulated)
        raise ValueError("Experimental and simulated arrays must have the same length.")
    experimental = np.array(experimental)
    simulated = np.array(simulated)

    return float(np.mean(np.abs((experimental - simulated) / experimental)) * 100)

element_values={}
for k,l in openmc_result_dict.items():
    if k not in openmc.data.ELEMENT_SYMBOL.values():
        print(f'Skipping {k} as it is not a valid element symbol.')
        continue
    exp_results = []
    for exp in l:
        fispact_result = np.array(fispact_result_dict[k][exp]['contact_dose_rate'])
        openmc_result = np.array(openmc_result_dict[k][exp]['contact_dose_rate']['meta_total'])
        openmc_result = openmc_result[DECAY_START_INDEX:]
        mape = mean_absolute_percentage_error(
            fispact_result,
            openmc_result
        )
        # print(k,exp,mape)
        exp_results.append(mape)
    element_values[k]=float(np.mean(exp_results))

if element_values:
    import pymatviz as pmv

    fig = pmv.ptable_heatmap_plotly(
        element_values,
        colorbar={"title": "mean absolute percent difference"},
        fmt=".2f",
    )
    fig.update_layout(title="OpenMC, FISPACT II contact dose rate mean absolute percent difference")
    fig.write_html('plotly_files/overview_of_code_to_code_differences.html')
else:
    print('Skipping periodic table overview because no selected cases are element symbols.')

# %%
