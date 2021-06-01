#!/usr/bin/env python3
"""Run the sample data.

See README.md in this directory for more information.
"""

import argparse
import gzip
import multiprocessing
import os
import shutil
import subprocess
import sys
import pandas as pd

def try_remove(f):
    try:
        os.remove(f)
    except OSError as e:
        pass

def parse_args():
    """Parse the arguments.

    On exit: Returns the result of calling argparse.parse()

    args.covidsim is the name of the CovidSim executable
    args.datadir is the directory with the input data
    args.paramdir is the directory with the parameters in it
    args.outputdir is the directory where output will be stored
    args.threads is the number of threads to use
    """
    parser = argparse.ArgumentParser()
    try:
        cpu_count = len(os.sched_getaffinity(0))
    except AttributeError:
        # os.sched_getaffinity isn't available
        cpu_count = multiprocessing.cpu_count()
    if cpu_count is None or cpu_count == 0:
        cpu_count = 2

    script_path = os.path.dirname(os.path.realpath(__file__))
    data_dir = os.path.join(script_path, "covid_sim")
    
    # Default values
    param_dir = os.path.join(data_dir, "param_files")
    output_dir = os.path.join(data_dir, "output_files")
    network_dir = os.path.join(data_dir, "network_files")
    read_only = 'Y'
    first_setup = 'N'
    exe_path = "CovidSim.exe"
    country = "United_Kingdom"

    parser.add_argument(
            "--country",
            help="Country to run sample for",
            default=country)
    parser.add_argument(
            "--covidsim",
            help="Location of CovidSim binary",
            default=exe_path)
    parser.add_argument(
            "--datadir",
            help="Directory at root of input data",
            default=data_dir)
    parser.add_argument(
            "--paramdir",
            help="Directory with input parameter files",
            default=param_dir)
    parser.add_argument(
            "--outputdir",
            help="Directory to store output data",
            default=output_dir)
    parser.add_argument(
            "--networkdir",
            help="Directory to store network data and bins",
            default=network_dir)
    parser.add_argument(
            "--threads",
            help="Number of threads to use",
            default=cpu_count
            )
    parser.add_argument(
            "--firstsetup",
            help="whether to initialize network and other first time setup or not",
            default=first_setup
            )
    parser.add_argument(
            "--readonly",
            help="whether to simply read and plot final excel results",
            default=read_only
            )
    args = parser.parse_args()

    return args

args = parse_args()

# whether to plot final results
plot = False

# Lists of places that need to be handled specially
united_states = [ "United_States" ]
canada = [ "Canada" ]
usa_territories = ["Alaska", "Hawaii", "Guam", "Virgin_Islands_US", "Puerto_Rico", "American_Samoa"]
nigeria = ["Nigeria"]

# Location of a user supplied executable (CovidSim.exe):
exe = args.covidsim

# Ensure output directory exists
os.makedirs(args.outputdir, exist_ok=True)

# The admin file to use
admin_file = os.path.join(args.datadir, "admin_units",
    "{0}_admin.txt".format(args.country))

if not os.path.exists(admin_file):
    print("Unable to find admin file for country: {0}".format(args.country))
    print("Data directory: {0}".format(args.datadir))
    print("Looked for: {0}".format(admin_file))
    exit(1)

# Population density file in gziped form, text file, and binary file as
# processed by CovidSim
if args.country in united_states + canada:
    wpop_file_root = "usacan"
elif args.country in usa_territories:
    wpop_file_root = "us_terr"
elif args.country in nigeria:
    wpop_file_root = "nga_adm1"
else:
    wpop_file_root = "eur"

wpop_file_gz = os.path.join(
        args.datadir,
        "populations",
        "wpop_{0}.txt.gz".format(wpop_file_root))
if not os.path.exists(wpop_file_gz):
    print("Unable to find population file for country: {0}".format(args.country))
    print("Data directory: {0}".format(args.datadir))
    print("Looked for: {0}".format(wpop_file_gz))
    exit(1)

wpop_file = os.path.join(
        args.networkdir,
        "wpop_{0}.txt".format(wpop_file_root))
wpop_bin = os.path.join(
        args.networkdir,
        "{0}_pop_density.bin".format(args.country))

if args.firstsetup == 'Y':
    try_remove(wpop_file)
    try_remove(wpop_bin)

# gunzip wpop fie
with gzip.open(wpop_file_gz, 'rb') as f_in:
    with open(wpop_file, 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)

# Configure pre-parameter file.  This file doesn't change between runs:
if args.country in united_states:
    pp_file = os.path.join(args.paramdir, "preUS_R0=2.0.txt")
elif args.country in nigeria:
    pp_file = os.path.join(args.paramdir, "preNGA_R0=2.0.txt")
else:
    pp_file = os.path.join(args.paramdir, "preUK_R0=2.0.txt")
if not os.path.exists(pp_file):
    print("Unable to find pre-parameter file")
    print("Param directory: {0}".format(args.paramdir))
    print("Looked for: {0}".format(pp_file))
    exit(1)

# Configure No intervention parameter file.  This is run first
# and provides a baseline
no_int_file = os.path.join(args.paramdir, "p_NoInt.txt")
if not os.path.exists(no_int_file):
    print("Unable to find parameter file")
    print("Param directory: {0}".format(args.paramdir))
    print("Looked for: {0}".format(no_int_file))
    exit(1)

# Configure an intervention (controls) parameter file.
# In reality you will run CovidSim many times with different parameter
# controls.
root = "PC7_CI_HQ_SD"
cf = os.path.join(args.paramdir, "p_{0}.txt".format(root))
if not os.path.exists(cf):
    print("Unable to find parameter file")
    print("Param directory: {0}".format(args.paramdir))
    print("Looked for: {0}".format(cf))
    exit(1)

school_file = None
if args.country in united_states:
    school_file = os.path.join(args.datadir, "populations", "USschools.txt")

    if not os.path.exists(school_file):
        print("Unable to find school file for country: {0}".format(args.country))
        print("Data directory: {0}".format(args.datadir))
        print("Looked for: {0}".format(school_file))
        exit(1)

# Some command_line settings
r = 3.0
rs = r/2

# This is the temporary network that represents initial state of the
# simulation
network_bin = os.path.join(
        args.networkdir,
        "Network_{0}_T{1}_R{2}.bin".format(args.country, args.threads, r))

if args.firstsetup == 'Y':
    try_remove(network_bin)

# Run the no intervention sim.  This also does some extra setup which is one
# off for each R.

cf = os.path.join(args.paramdir, "p_{0}.txt".format(root))
print("Intervention: {0} {1} {2}".format(args.country, root, r))
cmd = [
        exe,
        "/c:{0}".format(args.threads),
        "/A:" + admin_file
        ]
if school_file:
    cmd.extend(["/s:" + school_file])

if args.firstsetup == 'Y':

    cmd.extend([
            "/PP:" + pp_file, # Preparam file
            "/P:" + cf, # Param file
            "/O:" + os.path.join(args.outputdir,
                "{0}_{1}_R0={2}".format(args.country, root, r)), # Output
            "/D:" + wpop_file, # Input (this time text) pop density
            "/M:" + wpop_bin, # Where to save binary pop density
            "/S:" + network_bin, # Where to save binary net setup
            "/R:{0}".format(rs),
            "/BM:PNG",
            "98798150", # These four numbers are RNG seeds
            "729101",
            "17389101",
            "4797132"
            ])

elif args.firstsetup == 'N':
    
    cmd.extend([
            "/PP:" + pp_file,
            "/P:" + cf,
            "/O:" + os.path.join(args.outputdir,
                "{0}_{1}_R0={2}".format(args.country, root, r)),
            "/D:" + wpop_bin, # Binary pop density file (speedup)
            "/L:" + network_bin, # Network to load
            "/R:{0}".format(rs),
            "/CLP1:1.0", # default is 1.0 (Individual level compliance with quarantine) [0.6 - 1.0] E
            "/CLP2:0.1", # default is 0.1 (Relative spatial contact rate given social distancing) [0 - 0.4] S
            "/CLP3:0.1", # default is 0.9 (Proportion of detected cases isolated) [0.0 - 1.0] T
            "98798150",
            "729101",
            "17389101",
            "4797132"
            ])

if args.readonly == 'N':    
    print("Command line: " + " ".join(cmd))
    process = subprocess.run(cmd, check=True)

output_file = args.outputdir + "\{0}_{1}_R0={2}.avNE.severity.xls".format(args.country, root, r)
data = pd.read_csv(output_file, sep="\t")
df = pd.DataFrame(data)
max_I = df["I"].max()
print(max_I)

if plot:
    import matplotlib.pyplot as plt
    plt.plot(df["I"])
    plt.show()