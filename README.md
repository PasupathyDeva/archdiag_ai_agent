[README.md](https://github.com/user-attachments/files/30888004/README.md)
# ArchDiag Agent – Knowledge Base

This folder contains everything needed to set up the **ArchDiag** (Enterprise Architecture Diagram Designer) agent in Kiro CLI.

## Contents

```
ArchDiagKB/
├── README.md                  ← This file
├── steering/
│   └── archdiag.md            ← Agent steering file (behaviour + rules)
├── agents/
│   ├── archdiag.json          ← Agent configuration (tools, prompt, resources)
│   ├── generate_image.py      ← Image generation script (Azure OpenAI gpt-image-2)
│   ├── edit_image.py          ← Image editing script (modify existing diagrams)
│   ├── stencilsearch.py       ← Draw.io stencil icon lookup utility
│   └── azure_auth.py          ← Azure AD authentication module (shared)
└── ArchDiag_Agent_Setup_Guide.docx  ← Detailed setup instructions
```

## Quick Start

1. Install Kiro CLI (assumed already done)
2. Install Python dependencies: `pip install openai azure-identity`
3. Copy files to `~/.kiro/` (see the setup guide for exact paths)
4. Configure your Azure AI Foundry endpoint
5. Download the DrawioStencils icon library
6. Start with: `kiro chat --agent archdiag`

See **ArchDiag_Agent_Setup_Guide.docx** for complete step-by-step instructions.
