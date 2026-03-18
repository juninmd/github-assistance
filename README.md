# 🚀 Github Assistance

[![Status: Active](https://img.shields.io/badge/Status-Active-brightgreen.svg)]()
[![Protocol: Antigravity](https://img.shields.io/badge/Protocol-Antigravity-orange.svg)]()

> A modern, high-performance project built with **Python 3.x**. Orchestrated under the Antigravity protocol.

## ✨ Features

- **High Performance**: Optimized for speed and low resource usage.
- **Clean Architecture**: Built following strict Antigravity guidelines.
- **Automated**: Integrated with modern CI/CD and verification scripts.
- **Flexible AI Integration**: Easily switch between AI providers and models.

## 🤖 AI Configuration

The application allows you to seamlessly configure the AI provider and the underlying base model using environment variables.

- `AI_PROVIDER`: The AI provider you want to use. Supported values are:
  - `gemini` (defaults to model: `gemini-2.5-flash`)
  - `ollama` (defaults to model: `qwen3:1.7b`)
  - `openai` (defaults to model: `gpt-4o`)
- `AI_MODEL`: (Optional) Overrides the base model for the selected provider.

By default, if `AI_PROVIDER` is set to a supported value but `AI_MODEL` is omitted, the application will automatically select the default model associated with that provider.

## 🛠️ Tech Stack

- **Primary Technology**: Python 3.x
- **Architecture**: Modular and domain-driven.

## 🛡️ Antigravity Protocol

This project follows the **Antigravity** code standards:
- **150-Line Limit**: Applied to all logic modules.
- **Strict Typing**: Avoiding dynamic/any types.
- **Clean Code**: DRY, KISS, and SOLID principles applied rigorously.

---

*"Simplicity is the ultimate sophistication."*
