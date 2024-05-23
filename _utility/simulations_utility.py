import numpy as np
import multiprocessing
import json
import os
import concurrent.futures

from qiskit import transpile
from qiskit.transpiler import CouplingMap
from qiskit.providers.aer import AerSimulator
from qiskit_ibm_provider import IBMProvider


def fix_counts(counts_0: dict, n_qubits: int):
    """ Fixes the qiskit counts in the standard convention, orders the list and adds strings with zero counts.
    """

    # Mirror the bit strings to pass in standard convention
    mirrored_counts = {j[::-1]: counts_0[j] for j in counts_0}

    # Sort the results and return a list
    dict_items = mirrored_counts.items()
    counts = sorted(dict_items)

    # Add element 00 if it is missing
    if int(counts[0][0], 2) != 0:
        zero = format(0, 'b').zfill(n_qubits)
        counts.insert(0, (zero, 0))

    # Add element 11 if it is missing
    if int(counts[len(counts)-1][0], 2) != 2**n_qubits - 1:
        uno = format(2**n_qubits -1, 'b').zfill(n_qubits)
        counts.insert(len(counts), (uno, 0))
        
    for j in range(2**n_qubits-1):
        # Add missing elements
        if int(counts[j+1][0], 2) != int(counts[j][0],2) + 1:
            new = int(counts[j][0], 2) + 1
            new_bin = format(new, 'b').zfill(n_qubits)
            counts.insert(j+1, (new_bin, 0))
        else:
            pass
        
    return counts


def perform_parallel_simulation_with_multiprocessing(args: list, simulation: callable, max_workers: int=None):
    """ The .map method allows to execute the function simulation N_process times simultaneously.

    Preserves the order of the given comprehension list. We create a deepcopy of the argument, the simulation currently
    modifies it during execution.
    """

    # Configure pool
    cpu_count = multiprocessing.cpu_count()
    print(f"Our CPU count is {cpu_count}")

    n_processes = max(int(0.8 * cpu_count), 2)
    print(f"Use 80% of the cores, so {n_processes} processes.")

    simulations = len(args)
    chunksize = max(1, int(simulations / n_processes) + (1 if simulations % n_processes > 0 else 0))
    print(f"As we perform {simulations} simulations, we use a chunksize of {chunksize}.")

    # Compute
    p = multiprocessing.Pool(n_processes)
    for time, nqubit in p.imap_unordered(func=simulation, iterable=args, chunksize=chunksize):
        print(f"Simulated {nqubit} qubits in {time} s.", flush=True)

    # Shut down pool
    p.close()
    p.join()


def perform_parallel_simulation(args: list, simulation: callable, max_workers: int=None):
    """ The .map method allows to execute the function simulation N_process times simultaneously.

    Preserves the order of the given comprehension list. We create a deepcopy of the argument, the simulation currently
    modifies it during execution.
    """
    if max_workers is None:
        print("We use max_workers = None, so the default value min(32, os.cpu_count() + 4).")
    else:
        print(f"We use max_workers = {max_workers}.")

    # Execute parallel simulations
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_list = [val for val in executor.map(simulation, args)]
        concurrent.futures.wait(future_list)


def mock_perform_parallel_simulation(args: dict, simulation: callable, max_workers: int=None):
    """ This function mocks the parallel simulation.

    It is useful for debugging, because the error messages are displayed. In the real parallel simulation, they are
    muted.
    """
    print("We mock the parallel simulation.")

    for arg in args:
        simulation(arg)


def compute_Hellinger_distance(p_ng: float, p_real: float, nqubits: int) -> float:
    """ Given two distributions as array, returns the Hellinger distance.
    """
    dh_ng = (np.sqrt(p_real)-np.sqrt(p_ng))**2
    h_ng = 0

    for i in range(2**nqubits):
        h_ng = h_ng + dh_ng[i]

    h_ng = (1/np.sqrt(2)) * np.sqrt(h_ng)
    return h_ng  


def create_qc_list(circuit_generator, nqubits_list, qubits_layout, backend):
    """ Creates a list of quantum circuit.

    Args:
        circuit_generator (callable): Function which takes the number of qubits and returns a Qiskit circuit.
        nqubits_list (list[int]): List of the qubit numbers for which a quantum circuit should be generated.
        qubits_layout (list[int]): Layout of the qubits in the backend.
        backend: IBM backend.

    Returns:
        A list of transpiled circuits, generated by the Qiskit transpiler. The list items correspond 1:1 to the items in
        the list of qubits.
    """
    print("Warning:")
    print("1) At the moment, we perform the transpilation step in two steps because of a bug in Qiskit. ")
    print("   See https://qiskit.slack.com/archives/C7SS31917/p1670411292978089 for more infos.")
    print("2) We assume a linear connectivity.")
    sim = AerSimulator()
    result_list = []
    for nqubit in nqubits_list:
        coupling_map = CouplingMap.from_line(nqubit, bidirectional=True)
        qc1 = transpile(
            circuits=circuit_generator(nqubit),
            backend=sim,
            coupling_map=coupling_map,
            seed_transpiler=42
        )
        qc2 = transpile(
            circuits=qc1,
            backend=backend,
            scheduling_method='asap',
            initial_layout=qubits_layout[0:nqubit],
            seed_transpiler=42,
        )
        result_list.append(qc2)
    return result_list


def load_config(filename: str="") -> dict:
    """ Asks for the config filename in the prompt, loads it and returns it as json file.

    Note: In case you provide a filename as argument, then you can choose to use this filename by providing the empty
    input.
    """
    if filename == "":
        input_filename = input("Which configuration file would you like to use?")
    else:
        input_filename = filename

    config_filename = input_filename if len(input_filename) > 0 else filename
    f = open(f"configuration/{config_filename}")
    config = json.load(f)
    print(f"Loaded configuration {config_filename}.")
    return config


def setup_backend(Token: str, hub: str, group: str, project: str, device_name: str):
    """Takes the backend configuration and returns the configured backend.

    Args:
        Token (str): Token generated with the IBM Quantum Experience account.
        hub (str): Hub name of the account where the project is located.
        group (str): Group name of the account.
        project (str): Project under which the user has access to the device.
        device_name (str): Name of the quantum device.

    Returns:
        An IBM Quantum provider backend object that provides access to the
        specified quantum device.
    """
    IBMProvider.delete_account()
    IBMProvider.save_account(token=Token)
    provider = IBMProvider(instance=f"{hub}/{group}/{project}")
    return provider.get_backend(device_name)


def post_process_split(source_filenames: list, target_filenames: list, split: int):
    """Takes a list of filenames corresponding to the source data. Loads the files as arrays and combines split many
    files into the target files with the given filenames.

    Note:
        This is used as a postprocessing step when we use a split > 1 or when we reduce the shots size and perform
        more experiments.

    Example:
        source_filenames = ["file1.txt", ..., "file100.txt"]
        target_filenames = ["target1.txt", ..., "target10.txt"]
        split = 10
    """
    assert split * len(target_filenames) == len(source_filenames), \
        "Number of provided files and split does not go together."
    assert all((os.path.isfile(f) for f in source_filenames)), "Found invalid filename."
    assert not all((os.path.isfile(f) for f in target_filenames)), "At least one target files already exists."
    assert split > 1, f"Using a split of {split} does not make sense."

    i = 0
    for target_file in target_filenames:
        target_array = np.loadtxt(source_filenames[i])
        for source_file in source_filenames[i+1:i+split]:
            target_array += np.loadtxt(source_file)
        mean_array = target_array / split
        np.savetxt(target_file, mean_array)
        i += split
    return