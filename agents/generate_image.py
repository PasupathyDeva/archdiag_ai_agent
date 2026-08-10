"""
Azure OpenAI Image Generator (gpt-image-2)

Usage:
    python generate_image.py "A cute baby polar bear"
    python generate_image.py prompt.md
    python generate_image.py prompt.md -o my_image.png
    python generate_image.py "A red fox" --size 1792x1024 --quality high

Authentication is handled by azure_auth.py, which caches tokens and falls back
across several credential sources. If it fails, run `az login` and retry.
"""

import argparse
import base64
import os
import sys

import azure_auth


def get_prompt(prompt_input: str) -> str:
    """Get prompt from text or read from a .md file."""
    if prompt_input.endswith(".md"):
        if not os.path.isfile(prompt_input):
            azure_auth.fail(f"Prompt file not found: {prompt_input}")
        with open(prompt_input, "r", encoding="utf-8") as f:
            return f.read().strip()
    return prompt_input


def generate_image(prompt: str, output: str, size: str, quality: str) -> None:
    """Generate an image using Azure OpenAI gpt-image-2."""
    print("Generating image...")
    print(f"  Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
    print(f"  Size: {size}")
    print(f"  Quality: {quality}")
    sys.stdout.flush()

    client = azure_auth.build_client()

    result = azure_auth.call_with_auth_retry(
        lambda: client.images.generate(
            model=azure_auth.DEPLOYMENT,
            prompt=prompt,
            n=1,
            size=size,
            quality=quality,
        )
    )

    image_bytes = base64.b64decode(result.data[0].b64_json)
    with open(output, "wb") as f:
        f.write(image_bytes)

    print(f"  Output: {os.path.abspath(output)}")
    print("Done.")


def main():
    parser = argparse.ArgumentParser(
        description="Generate images using Azure OpenAI gpt-image-2"
    )
    parser.add_argument(
        "prompt",
        help="Text prompt or path to a .md file containing the prompt",
    )
    parser.add_argument(
        "-o", "--output",
        default="output.png",
        help="Output file path (default: output.png)",
    )
    parser.add_argument(
        "--size",
        default="1024x1024",
        choices=["1024x1024", "1792x1024", "1024x1792"],
        help="Image size (default: 1024x1024)",
    )
    parser.add_argument(
        "--quality",
        default="low",
        choices=["low", "medium", "high"],
        help="Image quality (default: low)",
    )

    args = parser.parse_args()
    prompt = get_prompt(args.prompt)

    if not prompt:
        azure_auth.fail("Prompt is empty.")

    try:
        generate_image(prompt, args.output, args.size, args.quality)
    except Exception as exc:  # noqa: BLE001 - top-level user-facing handler
        azure_auth.fail(str(exc))


if __name__ == "__main__":
    main()
