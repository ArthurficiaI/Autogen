Execute the following commands:

pip install autogen-agentchat
pip install-ext[openai]
pip install dotenv

Create a .env file and specify the following variables in it:

OPENAI_API_KEY = "your-api-key"
OPENAI_API_BASE = http://your.url

For the testcases you want to run simply adjust the numbers in the for-loop in the main method.
Then you can run the main method, the testlogs will be written in a file called results.log
The structure is pretty similar to the example, but if there are any difficulties feel free to E-Mail me :)
