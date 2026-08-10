"""
Azure OpenAI Image Editor (gpt-image-2)

Edits an existing image based on a text prompt using the Azure OpenAI images/edits API.

Usage:
    python edit_image.py "Change the title to XYZ" --image architecture.png
    python edit_image.py prompt.md --image architecture.png -o edited_output.png
    python edit_image.py prompt.md --image input.png --size 1792x1024 --quality high

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


def edit_image(prompt: str, image_path: str, output: str, size: str, quality: str) -> None:
    """Edit an existing image using the Azure OpenAI gpt-image-2 edits endpoint."""
    if not os.path.isfile(image_path):
        azure_auth.fail(f"Image file not found: {image_path}")

    print("Editing image...")
    print(f"  Source: {os.path.abspath(image_path)}")
    print(f"  Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
    print(f"  Size: {size}")
    print(f"  Quality: {quality}")
    sys.stdout.flush()

    client = azure_auth.build_client()

    def do_edit():
        # Reopen per attempt: a retried request cannot reuse a consumed stream.
        with open(image_path, "rb") as img_file:
            return client.images.edit(
                model=azure_auth.DEPLOYMENT,
                image=img_file,
                prompt=prompt,
                n=1,
                size=size,
                quality=quality,
            )

    result = azure_auth.call_with_auth_retry(do_edit)

    image_bytes = base64.b64decode(result.data[0].b64_json)
    with open(output, "wb") as f:
        f.write(image_bytes)

    print(f"  Output: {os.path.abspath(output)}")
    print("Done.")


def main():
    parser = argparse.ArgumentParser(
        description="Edit existing images using Azure OpenAI gpt-image-2"
    )
    parser.add_argument(
        "prompt",
        help="Text prompt describing the edit, or path to a .md file containing the prompt",
    )
    parser.add_argument(
        "--image", "-i",
        required=True,
        help="Path to the source image to edit",
    )
    parser.add_argument(
        "-o", "--output",
        default="edited_output.png",
        help="Output file path (default: edited_output.png)",
    )
    parser.add_argument(
        "--size",
        default="1024x1024",
        choices=["1024x1024", "1792x1024", "1024x1792"],
        help="Output image size (default: 1024x1024)",
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
        edit_image(prompt, args.image, args.output, args.size, args.quality)
    except Exception as exc:  # noqa: BLE001 - top-level user-facing handler
        azure_auth.fail(str(exc))


if __name__ == "__main__":
    main()
