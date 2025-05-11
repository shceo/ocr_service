from openai import OpenAI

client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key="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",
)

completion = client.chat.completions.create(
  extra_headers={
    "HTTP-Referer": "<YOUR_SITE_URL>", # Optional. Site URL for rankings on openrouter.ai.
    "X-Title": "<YOUR_SITE_NAME>", # Optional. Site title for rankings on openrouter.ai.
  },
  extra_body={},
  model="meta-llama/llama-3.3-70b-instruct",
  messages=[
    {
      "role": "user",
      "content": "What is the meaning of life? send me answer in json"
    }
  ]
)
print(completion.choices[0].message.content)
