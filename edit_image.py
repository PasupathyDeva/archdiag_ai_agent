"""
Azure OpenAI Image Editor (gpt-image-2)

Edits an existing image based on a text prompt using the Azure OpenAI images/edits API.

Usage:
    python edit_image.py "Change the title to XYZ" --image architecture.png
    python edit_image.py prompt.md --image architecture.png -o edited_output.png
    python edit_image.py prompt.md --image input.png --size 1792x1024 --quality high

Prerequisites:
    pip install openai azure-identity

Configuration:
    1. Replace <YOUR_AZURE_AI_FOUNDRY_ENDPOINT> with your Azure AI Foundry endpoint URL
       Example: https://<your-resource-name>.services.ai.azure.com/openai/v1
    2. Ensure you have the correct RBAC role assigned (Cognitive Services OpenAI User)
    3. Authenticate via: az login, Managed Identity, or Service Principal (SPN)

    For AWS Bedrock alternative:
    - Replace the OpenAI client with boto3 bedrock-runtime client
    - Use Amazon Titan Image Generator or Stability AI models
    - Authentication via AWS IAM credentials / assumed roles
"""

import argparse
import base64
import os
import sys
from openai import OpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider


# ============================================================
# CONFIGURATION - Replace with your own Azure AI Foundry endpoint
# ============================================================
AZURE_AI_FOUNDRY_ENDPOINT = "<YOUR_AZURE_AI_FOUNDRY_ENDPOINT>/openai/v1"
DEPLOYMENT_NAME = "gpt-image-2"
TOKEN_SCOPE = "https://ai.azure.com/.default"
# ============================================================


def get_prompt(prompt_input: str) -> str:
    """Get prompt from text or read from a .md file."""
    if prompt_input.endswith(".md") and os.path.isfile(prompt_input):
        with open(prompt_input, "r", encoding="utf-8") as f:
            return f.read().strip()
    return prompt_input


def edit_image(prompt: str, image_path: str, output: str, size: str, quality: str) -> None:
    """Edit an existing image using Azure OpenAI gpt-image-2 edits endpoint."""
    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(), TOKEN_SCOPE
    )

    client = OpenAI(
        base_url=AZURE_AI_FOUNDRY_ENDPOINT,
        api_key=token_provider,
    )

    # Validate image file exists
    if not os.path.isfile(image_path):
        print(f"Error: Image file not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Editing image...")
    print(f"  Source: {os.path.abspath(image_path)}")
    print(f"  Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
    print(f"  Size: {size}")
    print(f"  Quality: {quality}")

    # Open the image file and send to edits API
    with open(image_path, "rb") as img_file:
        img = client.images.edit(
            model=DEPLOYMENT_NAME,
            image=img_file,
            prompt=prompt,
            n=1,
            size=size,
            quality=quality,
        )

    image_bytes = base64.b64decode(img.data[0].b64_json)
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
        print("Error: Prompt is empty.", file=sys.stderr)
        sys.exit(1)

    edit_image(prompt, args.image, args.output, args.size, args.quality)


if __name__ == "__main__":
    main()
