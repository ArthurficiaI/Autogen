import asyncio
import os
from custom_tools import *
import autogen
import autogen_agentchat.teams
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
from autogen_agentchat.teams import RoundRobinGroupChat, SelectorGroupChat
from autogen_agentchat.ui import Console
from custom_tools import *
from autogen_core.tools import FunctionTool
from autogen.coding import LocalCommandLineCodeExecutor
from autogen_ext.models.ollama import OllamaChatCompletionClient
import dotenv
dotenv.load_dotenv()
import openpyxl
from pathlib import Path
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen import ConversableAgent, register_function
import json
import re

import requests
import subprocess
import os

import os
from autogen import ConversableAgent
from autogen.coding import LocalCommandLineCodeExecutor

#from repo_1fake.astropy.coordinates.builtin_frames.ecliptic_transforms import true_baryecliptic_to_icrs

# Create a temporary directory to store the code files.



API_URL = "http://localhost:8081/task/index/"  # API endpoint for SWE-Bench-Lite
LOG_FILE = "results.log"
root_dir = os.path.dirname(os.path.abspath(__file__)) + r"\repos"


code_writer_system_message = """
You are a helpful AI assistant.
Solve tasks using your coding and language skills.
You're going to fix problems inside a repository. A planning agent will have instructions for you.
In the following cases, you'll get coding instructions pertaining to certain files. Modify these files as wished by the planning agent and make the changes in the repository.
Finish the task smartly.
Solve the task step by step if you need to. If a plan is not provided, then check in with the planning agent. Be clear which step uses code, and which step uses your language skill.
When using code, you must indicate the script type in the code block. The planning_agent cannot provide any other feedback or perform any other action beyond executing the code you suggest. The planning_agent can't modify your code. So do not suggest incomplete code which requires users to modify. Don't use a code block if it's not intended to be later executed in the tests.
Make sure to make actual changes to the code files in the git repository. That means using git add and commit. Otherwise the files cannot be used.
If the result indicates there is an error, fix the error and output the code again. Make sure that your code changes are minimal as to only resolve the failing tests.
Do not replace the file with just a snippet of your own code! Always make sure that the rest of the file that you wrote on stays intact, do not delete the parts of the file, that you didn't want to modify!
When you find an answer, verify the answer carefully. Include verifiable evidence in your response if possible.
When you struggle to find a file, you always list out the contents in the current directory and work further from there.
To write code, use the replace_in_file tool, make sure to make the string you want to be replaced specific enough so only the right string gets replaced.
Also see that when you give the old string more context, that the new string needs the same context added too. Also some code might be in python so take care of the correct indentation!
Tell the planning agent when you think you're done.
For all your tools the path to the file or repo only has to be given relative to the current repo. The start of your relative path is always repos/repo_{reponumber}, always remember this scheme!. Never use an absolute path for the tools!
"""

code_tester_system_message = """
You are a helpful AI assistant.
Run tests using your code testing skills inside a git repository. Your teammates are implementing a fix in this repo.
In the following cases, you will work in a repository where you will need to run the testsuite and then report back to the planning agent.
Fail to parse tests are tests that didn't parse before and only parse successfully when the problem has been fixed.
Parse to parse tests are tests that passed successfully before and now should still pass successfully after the fixes. They insure that nothing has been broken.
In other words when all tests are successful then this fix would constitute a perfect solution!
If there is nothing in harnessoutput, then most probably nothing of note has been changed.
If a pass to pass test fails, that means that something was broken that wasn't broken before, so tell planning agent to fix the mistake made.
If every out of every test has been successful then reply with TERMINATE
When testing only call one test as the test number coincides with repository number you are working on. So using any other number gives you a test for a repo that is completely independent from your changes!
"""

code_planner_system_message = """
You are a helpful AI assistant.
You plan on how to fix a git repository. You are the leading force in an AI Team with a coding_agent and a testing_agent.
As you are the only one with direct access to the prompt, see that you tell your workers the directory and the other details they need to work.
You do not modify any files in the repository yourself.
You're given a problem that you and your team are supposed to fix inside your repository.
Develop your plans carefully, take the files into account to find where the problem lies.
The code_writer can write code can modify files and add/commit them to the git, and the code_tester can use the tests inside the repository to confirm or deny positive changes.
Make sure to tell the code_writer to make actual changes to the code files in the git repository, as in using git add. Always give them the path to the file you want to be modified.
After the coding_agent thinks he's done his task, confirm with the testing_agent and see if the problem has been fixed.
The testing_agent is never supposed to create new tests. Only use preexisting tests from the repo and run these. You typically only ask to run the test_suite once, as it takes a lot of time.
If no, then analyze the problem and what went wrong this time and develop a new plan for the coding_agent.
Make sure to produce instructions for coding_agent or testing_agent at some point instead of only talking to yourself.
Make sure the fix is minimal and only touches what's necessary to resolve the failing tests.
For all your tools the path to the file or repo only has to be given relative to the current repo. The start of your relative path is always repos/repo_{reponumber}, always remember this scheme!. Never use an absolute path for the tools!
If you think the task is done or you find no good way to progress further then reply with TERMINATE to end the process, otherwise don't use the word TERMINATE
"""

selector_alt_message ="""Select an agent to perform task.

{roles}

Current conversation context:
{history}

Read the above conversation, then select an agent from {participants} to perform the next task.
Make sure the planner agent has assigned tasks before other agents start working.
Only select one agent.
Start with planning agent.
"""




POWER_client = OpenAIChatCompletionClient(model = "gpt-4o-mini",api_key=os.environ.get("OPENAI_API_KEY"),base_url=os.environ.get("OPENAI_API_BASE")


async def handle_task(index):
    api_url = f"{API_URL}{index}"
    print(f"Fetching test case {index} from {api_url}...")


    repo_dir = os.path.join(root_dir, f"repo_{index}")  # Use unique repo directory per task
    start_dir = os.getcwd()  # Remember original working directory

    try:
        response = requests.get(api_url)
        if response.status_code != 200:
            raise Exception(f"Invalid response: {response.status_code}")

        testcase = response.json()
        prompt = testcase["Problem_statement"]
        git_clone = testcase["git_clone"]
        fail_tests = json.loads(testcase.get("FAIL_TO_PASS", "[]"))
        pass_tests = json.loads(testcase.get("PASS_TO_PASS", "[]"))
        instance_id = testcase["instance_id"]

        # Extract repo URL and commit hash
        parts = git_clone.split("&&")
        clone_part = parts[0].strip()
        checkout_part = parts[-1].strip() if len(parts) > 1 else None

        repo_url = clone_part.split()[2]

        print(f"Cloning repository {repo_url} into {repo_dir}...")
        print(f"prompt: \n\n {prompt} \n\n")

        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        if not os.path.isdir(repo_dir):
            subprocess.run(["git", "clone", repo_url, repo_dir], check=True, env=env)

            if checkout_part:
                commit_hash = checkout_part.split()[-1]
                print(f"Checking out commit: {commit_hash}")
                subprocess.run(["git", "checkout", commit_hash], cwd=repo_dir, check=True, env=env)




        text_mention_termination = TextMentionTermination("TERMINATE")
        max_messages_termination = MaxMessageTermination(max_messages=50)
        termination = text_mention_termination | max_messages_termination

        planning_agent = AssistantAgent(
            model_client=POWER_client,
            name="planning_agent",
            system_message=code_planner_system_message,
            tools=[read_file_tool,find_files_tool],


        )

        coding_agent = AssistantAgent(
            model_client=POWER_client,
            name="coding_agent",
            system_message=code_writer_system_message,
            tools=[read_file_tool,find_files_tool,replace_in_file_tool],
        )

        testing_agent = AssistantAgent(
            model_client=POWER_client,
            name="testing_agent",
            system_message = code_tester_system_message,
            tools=[call_tests_tool],
            reflect_on_tool_use=True,
        )


        group = autogen_agentchat.teams.SelectorGroupChat(
            participants=[planning_agent,coding_agent,testing_agent],
            model_client=POWER_client,
            termination_condition=termination,
            selector_prompt=selector_alt_message,
            allow_repeated_speaker=True,

        )


        startAI = True #just to debug



        if(startAI):
            await Console(group.run_stream(task = f"Problem description:\n{prompt}\n\nYou are working on testcase {index}, remember that for your paths!"))





        # Call REST service instead for evaluation changes from agent
        print(f"Calling SWE-Bench REST service with repo: {repo_dir}")
        test_payload = {
            "instance_id": instance_id,
            "repoDir": f"/repos/repo_{index}",  # mount with docker
            "FAIL_TO_PASS": fail_tests,
            "PASS_TO_PASS": pass_tests
        }
        print(f"payload: {test_payload}")
        res = requests.post("http://localhost:8082/test", json=test_payload)
        print(f"res: {res}")
        res.raise_for_status()
        result_raw = res.json().get("harnessOutput", "{}")
        print(result_raw)
        result_json = json.loads(result_raw)
        print(result_json)
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
        os.chdir(start_dir)
        with open(LOG_FILE, "a", encoding="utf-8") as log:
            log.write(f"\n--- TESTCASE {index} ---\n")
            log.write(f"FAIL_TO_PASS passed: {fail_pass_passed}/{fail_pass_total}\n")
            log.write(f"PASS_TO_PASS passed: {pass_pass_passed}/{pass_pass_total}\n")
        print(f"Test case {index} completed and logged.")

    except Exception as e:
        os.chdir(start_dir)
        with open(LOG_FILE, "a", encoding="utf-8") as log:
            log.write(f"\n--- TESTCASE {index} ---\n")
            log.write(f"Error: {e}\n")
        print(f"Error in test case {index}: {e}")


def extract_last_token_total_from_logs():
    log_dir = r"logs"
    log_files = [f for f in os.listdir(log_dir) if f.endswith(".log")]
    if not log_files:
        return "No logs found"

    log_files.sort(reverse=True)

    latest_log_path = os.path.join(log_dir, log_files[0])
    with open(latest_log_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    for line in reversed(lines):
        match = re.search(r'Cumulative Total=(\d+)', line)
        if match:
            return int(match.group(1))

    return "Cumulative Total not found"


async def main():
    for i in range(1, 2):
        await handle_task(i)




if __name__ == "__main__":
    asyncio.run(main())
