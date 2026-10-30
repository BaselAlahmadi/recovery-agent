from dotenv import load_dotenv
import anthropic

load_dotenv()  # reads your key from .env
client = anthropic.Anthropic()

msg = client.messages.create(
    model="claude-haiku-5-5",
    max_tokens=50,
    messages=[{"role": "user", "content": "Say hello in one short sentence."}],
)
print(msg.content[0].text)