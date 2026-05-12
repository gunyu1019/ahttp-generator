# ahttp-generator

The **ahttp-generator** is a tool for generating Python SDKs from OpenAPI specifications.

---

## 🛠 Installation

Python 3.10 or higher is required.

```bash
# Linux/MacOS
$ pip install ahttp-generator

# Windows
$ py -3 -m pip install ahttp-generator
```
To install the development version.

```bash
$ git clone https://github.com/gunyu1019/ahttp-generator.git -b develop
$ cd ahttp-generator
$ python3 -m pip install -U .
```
---

## 🚀 Getting Started

### Generating an SDK

```bash
# Linux/MacOS
$ python3 -m ahttp_generator -i ./openapi.json -o ./my_sdk

# Windows
$ py -3 -m ahttp_generator -i ./openapi.json -o ./my_sdk
```

### Using the Generated SDK

```python
import asyncio
from my_sdk import MyClient

async def main():
    async with MyClient(api_key="YOUR_TOKEN") as client:
        player = await client.get_player(
            platform="steam", 
            player_id="account.123..."
        )
        print(f"Name: {player.data.attributes.name}")

if __name__ == "__main__":
    asyncio.run(main())
```
