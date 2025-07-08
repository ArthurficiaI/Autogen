
import requests
import os
import json
import fnmatch

from autogen_core.tools import FunctionTool


def read_file_skip_leading_blank_lines(file_path:str) -> str:
    try:
        with open(file_path, 'r') as file:
            lines = file.readlines()

        # Skip leading blank lines
        text_started = False
        content = []

        for line in lines:
            if not text_started and line.strip() == '':
                continue
            text_started = True
            content.append(line)

        return ''.join(content)
    except FileNotFoundError:
        return f"The file at {file_path} does not exist"


def writetofile(filename: str, text: str) -> str:
    script_directory = os.getcwd()
    file_path = os.path.join(script_directory, filename)
    try:
        with open(file_path, 'w') as file:
            file.write(f"\n{text}")
        return f"Text successfully overwritten at {file_path}"
    except FileNotFoundError:
        return f"The file at {file_path} does not exist"





async def call_tests(testcase_index : int) -> str:
    root_root_dir = os.getcwd()
    root_dir = os.path.join(os.getcwd(),r"repos")
    repo_dir = os.path.join(root_dir, f"repo_{testcase_index}")


    try:
        response = requests.get(f"http://localhost:8081/task/index/{testcase_index}")
        if response.status_code != 200:
            raise Exception(f"Invalid response: {response.status_code}")

        testcase = response.json()
        prompt = testcase["Problem_statement"]
        git_clone = testcase["git_clone"]
        fail_tests = json.loads(testcase.get("FAIL_TO_PASS", "[]"))
        pass_tests = json.loads(testcase.get("PASS_TO_PASS", "[]"))
        instance_id = testcase["instance_id"]


        test_payload = {
            "instance_id": instance_id,
            "repoDir": f"/repos/repo_{testcase_index}",  # mount with docker
            "FAIL_TO_PASS": fail_tests,
            "PASS_TO_PASS": pass_tests
        }
        res = requests.post("http://localhost:8082/test", json=test_payload)
        res.raise_for_status()
        result_raw = res.json().get("harnessOutput", "{}")
        result_json = json.loads(result_raw)
        if not result_json:
            raise ValueError("No data in harnessOutput – possible evaluation error or empty result")
        instance_id = next(iter(result_json))
        tests_status = result_json[instance_id]["tests_status"]
        fail_pass_results = tests_status["FAIL_TO_PASS"]
        fail_pass_total = len(fail_pass_results["success"]) + len(fail_pass_results["failure"])
        fail_pass_passed = len(fail_pass_results["success"])
        pass_pass_results = tests_status["PASS_TO_PASS"]
        pass_pass_total = len(pass_pass_results["success"]) + len(pass_pass_results["failure"])
        pass_pass_passed = len(pass_pass_results["success"])

        # Log results
        return_string = ""

        os.chdir(root_root_dir)
        with open("agentTestResults.log", "a", encoding="utf-8") as log:
            log.write(f"\n--- TESTCASE {testcase_index} ---\n")
            log.write(f"FAIL_TO_PASS passed: {fail_pass_passed}/{fail_pass_total}\n")
            log.write(f"PASS_TO_PASS passed: {pass_pass_passed}/{pass_pass_total}\n")
            return f"\n--- TESTCASE {testcase_index} ---\n" + f"FAIL_TO_PASS passed: {fail_pass_passed}/{fail_pass_total}\n" + f"PASS_TO_PASS passed: {pass_pass_passed}/{pass_pass_total}\n"
    except Exception as e:
        os.chdir(root_root_dir)
        with open("agentTestResults.log", "a", encoding="utf-8") as log:
            log.write(f"\n--- TESTCASE {testcase_index} ---\n")
            log.write(f"Error: {e}\n")
            print(f"Error in test case{testcase_index}: {e}")
            return f"\n--- TESTCASE {testcase_index} ---\n" + f"Error: {e}\n" + f"Error in test case{testcase_index}: {e}"



async def replace_in_file(path_from_root : str, old_string : str, new_string : str) -> str:
    root_dir = os.getcwd()
    filename = os.path.join(root_dir, path_from_root)

    try:
        with open(filename) as f:
            s = f.read()
            if old_string not in s:
                return f"{old_string} not found in {filename}"


        with open(filename, 'w') as f:
            s = s.replace(old_string, new_string)
            f.write(s)
            return "String successfully replaced"

    except Exception:
        return "There was an error trying to replace content in the file, probably the file was not found."





async def find_files(path_from_root: str, pattern: str) -> str:
    root_dir = os.getcwd()
    directory = os.path.join(root_dir,path_from_root)

    return_files = ""
    for root, dirs, files in os.walk(directory):
        for basename in files:
            if fnmatch.fnmatch(basename, pattern):
                filename = os.path.join(root, basename)
                return_files += filename + "\n"

    if(return_files.count("\n") > 50):
        return "There were over 50 files found with that pattern, please use a more precise pattern"
    return return_files


async def read_file(path_from_root : str) -> str:
    # splitted_path = path_from_root.split("\\")
    # maybe_repo = splitted_path[0]
    # if ("repo" in maybe_repo and maybe_repo[4:].isdigit()):
    #     new_path = ""
    #     for i in range(1,len(splitted_path)):
    #         new_path = os.path.join(new_path,splitted_path[i])
    #     path_from_root = new_path



    root_dir = os.getcwd()
    file_path = os.path.join(root_dir, path_from_root)


    try:
        with open(file_path, 'r') as file:
            lines = file.readlines()

        # Skip leading blank lines
        text_started = False
        content = []

        for line in lines:
            if not text_started and line.strip() == '':
                continue
            text_started = True
            content.append(line)

        return ''.join(content)
    except FileNotFoundError:
        return f"The file at {file_path} does not exist"







read_file_tool = FunctionTool(read_file, description = "Returns the content of a file given the relative path")
replace_in_file_tool = FunctionTool(replace_in_file, description="Tool that replaces a string in given file, with a new string. Useful since agents cannot generate long code snippets and otherwise lose the rest of the file. The path to the file only has to be given relative")
find_files_tool = FunctionTool(find_files, description="Returns the path to files, of which their names contain a given keyword.")
call_tests_tool = FunctionTool(call_tests, description="Calls the tests for the corresponding repository number")
