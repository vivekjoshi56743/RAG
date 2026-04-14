"""
Bulk loader for demo corpus.

Usage:
    python scripts/load_demo.py --dir /path/to/docs --api http://localhost:8080 --token <firebase-id-token>
"""
import argparse
import asyncio
import aiohttp
from pathlib import Path

SUPPORTED = {".pdf", ".docx", ".txt", ".md"}


async def upload_file(session: aiohttp.ClientSession, api_base: str, token: str, path: Path) -> None:
    data = aiohttp.FormData()
    data.add_field("file", open(path, "rb"), filename=path.name, content_type="application/octet-stream")
    async with session.post(
        f"{api_base}/api/documents/upload",
        data=data,
        headers={"Authorization": f"Bearer {token}"},
    ) as resp:
        if resp.status == 200:
            print(f"  ✓ {path.name}")
        else:
            print(f"  ✗ {path.name} — {await resp.text()}")


async def main(directory: str, api_base: str, token: str, concurrency: int) -> None:
    paths = [p for p in Path(directory).rglob("*") if p.suffix.lower() in SUPPORTED]
    print(f"Found {len(paths)} files in {directory}")

    sem = asyncio.Semaphore(concurrency)
    async with aiohttp.ClientSession() as session:
        async def bounded_upload(p: Path):
            async with sem:
                await upload_file(session, api_base, token, p)

        await asyncio.gather(*(bounded_upload(p) for p in paths))

    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True, help="Directory of files to upload")
    parser.add_argument("--api", default="http://localhost:8080")
    parser.add_argument("--token", required=True)
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()

    asyncio.run(main(args.dir, args.api, args.token, args.concurrency))
