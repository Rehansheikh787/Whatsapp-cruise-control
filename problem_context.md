# Problem Context — WhatsApp Cruise Control

> **Project:** Put Your WhatsApp on Cruise Control — Hands-Free Replies by an AI Agent using RAG  
> **Course:** Masai September Cohort  
> **Author:** Rehan Sheikh

---

## 1. What Is This Project?

We're training an AI agent on your own WhatsApp chats so it can reply in your exact style — your phrasing, your Hinglish, your emojis, and the way your tone naturally shifts between family, friends, and colleagues.

When a message arrives, your agent:
1. **Reads** the incoming message.
2. **Decides** whether you'd actually reply (or stay silent).
3. **Retrieves** how you've talked before (from your chat history).
4. **Answers as you** — live, on real WhatsApp.

> This isn't a chatbot. It's a **retrieval-grounded persona agent**, built by you, over four weeks.

---

## 2. What We Want to Achieve

| # | Goal |
|---|------|
| 1 | A **working, live AI agent** connected to real WhatsApp — not a demo running only on your laptop |
| 2 | An agent that **sounds authentically like you** — not a generic assistant wearing your name |
| 3 | An agent with **judgment** — one that knows exactly when to reply, and when to stay silent |
| 4 | A fully public, **demoable proof of work**: a GitHub repo, a live console, and a recorded demo |
| 5 | All of it built entirely on **free-tier tools** — no budget required, no paid API keys needed |

---

## 3. What We'll Learn

- **RAG (Retrieval-Augmented Generation)** — and why it beats fine-tuning when you want something personalized, not retrained
- **Prompt engineering for tone and persona** — how to make an AI sound like a specific person, not a specific model
- **Rule-based decision systems working alongside AI** — cheap logic first, AI only when it's genuinely needed
- **Vector databases and embeddings** — how machines search by meaning, not just exact text
- **Building and wiring a real, live automation pipeline** — from a raw data export all the way to a message sent in the real world
- **Using GitHub Copilot as an actual build partner** — not autocomplete, a collaborator you direct with clear prompts

---

## 4. How We'll Go About This (4-Week Plan)

### Week 1 — The Ghostwriter: Teach it your voice
> Build the persona layer. Parse your exported chats, identify your tone patterns, slang, emoji usage, and create a persona prompt that captures *how you talk*.

### Week 2 — The Curator: Mine your chat history
> Set up RAG infrastructure. Chunk your conversations, embed them into a vector database, and build the retrieval pipeline that surfaces the right context for any incoming message.

### Week 3 — The Router: Teach it when to speak
> Build the decision engine. Implement rule-based filters and AI-backed judgment so the agent knows which messages deserve a reply and which should be left on read.

### Week 4 — The Puppetmaster: Go live on WhatsApp
> Wire everything together. Connect to real WhatsApp, deploy the full pipeline, and ship a live demo.

Each week ships something real and demoable. By the end of Week 4, you won't just have learned about RAG agents — you'll have shipped one, live, on your own WhatsApp.

---

## 5. Architecture Overview

*(Sourced from `Archietecture Diagram.docx` — the document contains primarily a visual architecture diagram.)*

The system architecture follows a standard RAG-agent pipeline:

```
┌──────────────┐     ┌──────────────────┐     ┌───────────────────┐
│  WhatsApp    │────▶│  Message Router  │────▶│  Decision Engine  │
│  (live)      │     │  (rule-based +   │     │  (reply / ignore) │
│              │     │   AI fallback)   │     │                   │
└──────────────┘     └──────────────────┘     └───────┬───────────┘
                                                       │
                                                       ▼
                     ┌──────────────────┐     ┌───────────────────┐
                     │  Vector DB       │◀───▶│  Retrieval Layer  │
                     │  (embeddings of  │     │  (RAG pipeline)   │
                     │   chat history)  │     │                   │
                     └──────────────────┘     └───────┬───────────┘
                                                       │
                                                       ▼
                     ┌──────────────────┐     ┌───────────────────┐
                     │  Persona Prompt  │────▶│  LLM (response    │
                     │  (tone, style,   │     │   generation)     │
                     │   emoji rules)   │     │                   │
                     └──────────────────┘     └───────┬───────────┘
                                                       │
                                                       ▼
                                              ┌───────────────────┐
                                              │  WhatsApp Reply   │
                                              │  (sent as you)    │
                                              └───────────────────┘
```

### Key Components

| Component | Responsibility |
|-----------|---------------|
| **WhatsApp Connector** | Receives incoming messages; sends AI-generated replies back on WhatsApp |
| **Message Router** | First-pass filtering using cheap rule-based logic before involving the LLM |
| **Decision Engine** | Decides: reply, ignore, or escalate. Uses both rules and AI judgment |
| **Vector Database** | Stores embedded chat history chunks for semantic retrieval |
| **Retrieval Layer (RAG)** | Given an incoming message, retrieves the most relevant past conversations |
| **Persona Prompt** | Encodes your tone, phrasing patterns, emoji habits, and style per contact category |
| **LLM** | Generates the final reply grounded on retrieved context + persona prompt |

---

## 6. Data Inventory

The project includes exported WhatsApp chat history organized by contact type:

### Chat Files

| Category | Contact | File | Messages (lines) | Size |
|----------|---------|------|------------------|------|
| **Hindi Friends** | Mobeen Ahmed | `WhatsApp Chat with Mobeen Ahmed.txt` | ~1,289 | 67 KB |
| **Hindi Friends** | Mohammad Zaheer | `WhatsApp Chat with Mohammad Zaheer.txt` | ~9,290 | 509 KB |
| **Hindi Friends** | Shashwat | `WhatsApp Chat with Shashwat.txt` | ~2,827 | 151 KB |
| **Marathi Friends** | Ritik Choudhary | `WhatsApp Chat with Ritik Choudhary.txt` | ~3,521 | 201 KB |
| **Working Professionals** | Rohit Meshram Sir NML | `WhatsApp Chat with Rohit Meshram Sir NML.txt` | ~718 | 45 KB |

**Total:** ~17,645 message lines across 5 contacts (~973 KB)

### Chat Format

All chats follow standard WhatsApp export format:
```
DD/MM/YY, H:MM am/pm - <Sender>: <Message>
```

Example:
```
14/05/21, 9:05 am - Mobeen Ahmed: Eid mubarak bhai......
14/05/21, 9:05 am - @Rehan Sheikh: Apko bhi bhai
```

### Data Characteristics

- **Languages:** Hindi, Marathi, Hinglish (Hindi-English mix), and English
- **Tone variation by contact type:**
  - *Hindi friends* — casual, emoji-heavy, Hinglish slang, abbreviated words
  - *Marathi friends* — mix of Marathi and Hindi, casual tone
  - *Working professionals* — more formal, task-oriented, respectful ("Sir", "Ok sir")
- **Media references:** `<Media omitted>` placeholders throughout (images, audio, video not included)
- **Date range:** ~2019 to ~2025 (multi-year conversation history)

---

## 7. Key Constraints & Decisions

| Constraint | Detail |
|------------|--------|
| **Budget** | Free-tier tools only — no paid API keys |
| **Privacy** | Chats contain personal conversations; all processing should be local or privacy-respecting |
| **Multi-lingual** | Agent must handle Hindi, Marathi, Hinglish, and English seamlessly |
| **Tone switching** | Agent must adapt tone per contact category (casual vs. professional) |
| **Judgment calls** | Agent must know when to reply and when to stay silent (not everything gets a response) |
| **Live deployment** | Final output is a live agent on real WhatsApp, not just a notebook demo |

---

## 8. Project File Structure

```
Watsapp Cruise control/
├── Archietecture Diagram.docx          # Visual architecture diagram
├── Context of the problem statement.pdf # Full project brief (this document's source)
├── problem_context.md                  # ← This file
└── WhatsApp Chats/
    ├── Chats with hindi friends/
    │   ├── WhatsApp Chat with Mobeen Ahmed/
    │   │   └── WhatsApp Chat with Mobeen Ahmed.txt
    │   ├── WhatsApp Chat with Mohammad Zaheer/
    │   │   └── WhatsApp Chat with Mohammad Zaheer.txt
    │   └── WhatsApp Chat with Shashwat/
    │       └── WhatsApp Chat with Shashwat.txt
    ├── Chats with marathi friends/
    │   └── WhatsApp Chat with Ritik Choudhary/
    │       └── WhatsApp Chat with Ritik Choudhary.txt
    └── Chats with working professionals/
        └── WhatsApp Chat with Rohit Meshram Sir NML/
            └── WhatsApp Chat with Rohit Meshram Sir NML.txt
```

---

## 9. Source Documents

| Document | Description |
|----------|-------------|
| `Context of the problem statement.pdf` | Full project brief — goals, learning objectives, 4-week plan |
| `Archietecture Diagram.docx` | Visual architecture/system diagram |
