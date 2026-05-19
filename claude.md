# Local AI Blog Generator Project

## Project Overview
A local AI application that automatically generates blog posts, including structured text and AI-generated images, running entirely on a high-spec Mac environment.

## Hardware Environment
- **Machine:** Apple Silicon Mac
- **OS:** macOS

## Core Tech Stack (Proposed)
- **Development Tool:** Claude Code / Cursor
- **LLM Engine:** Ollama (Local)
- **Preferred Models:**
    - Text: `gemma2:27b`, `qwen2.5:32b`, or `llama3.1:70b` (quantized)
    - Image: `Flux.1 dev` (quantized) or `Stable Diffusion XL`
- **UI Framework:** Streamlit (Python)
- **Backend:** Python (Ollama API, Diffusers library for local image generation)

## Application Workflow
1.  **Input:** User provides keywords and target audience.
2.  **Outline Generation:** LLM creates a structured outline (H2/H3 headings).
3.  **Content Generation:** LLM writes detailed body text for each section.
4.  **Image Prompting:** LLM generates specific image prompts based on section content.
5.  **Image Generation:** Local Image Diffusion model generates images to be placed after headings.
6.  **Integration:** Assemble text and images into a final Markdown format.

## Implementation Details for Claude Code
- Use `ollama-python` or direct HTTP requests to interact with Ollama.
- For local image generation, utilize `diffusers` with `mps` (Metal Performance Shaders) backend to leverage Apple Silicon GPU.
- Ensure efficient memory management to load both Text and Image models within the available unified memory.
