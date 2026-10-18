import argparse
import asyncio
from .database import Database
from .seed import seed


async def run(command):
    database = await Database.connect()
    try:
        if command == 'migrate':
            await database.migrate()
        else:
            await seed(database)
    finally:
        await database.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Explicit Lapse database maintenance')
    parser.add_argument('command', choices=('migrate', 'seed'))
    asyncio.run(run(parser.parse_args().command))
