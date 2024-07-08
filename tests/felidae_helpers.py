import os


def get_felidae_test_folders(test_name):
    """
    Returns the paths to the input, expected output, and output folders for the
    test_felidae.py test file.
    """

    test_code_path = os.path.dirname(os.path.realpath(__file__))
    test_files_path = os.path.join(test_code_path, "test_files_felidae")
    input_path = os.path.join(test_files_path, "input_files")
    expected_output_path = os.path.join(test_files_path, "expected_output_files_" + test_name)
    output_location = os.path.join(test_files_path, "output_files")

    # Remove the output files if they already exist
    for name in os.listdir(output_location):
        if name.startswith("."):
            continue

        os.remove(os.path.join(output_location, name))

    return input_path, expected_output_path, output_location
