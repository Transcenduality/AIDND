AIDND - A stateful RPG engine built in Python that uses Large Language Models to act as a mechanical Dungeon Master. The engine automates the rules, d20 rolls, and math, allowing players to explore any world they can imagine.

Features:
Automated DM Logic: The AI manages character sheets, inventory, and stats through structured JSON.

Dynamic UI: Built with Pygame to provide real-time updates for HP, XP, and Gold.

Persistent World: Includes a built-in save system and history tracking to maintain world-state.

Local Friendly: Designed to work with OpenAI-compatible APIs, including local setups like Ollama or LM Studio.

Setup
1. Install Dependencies
Open your terminal or command prompt and run:
pip install pygame openai pyttsx3

2. Set Your API Key
The engine looks for an environment variable named OPENAI_API_KEY.

Windows: Search for "Edit the system environment variables" > Environment Variables > New... > Variable name: OPENAI_API_KEY, Variable value: your_key_here.

3. How to Run
Once dependencies are installed and your key is set:

Locate AIDnD.py in your file explorer.

Right-click the file.

Select "Run with Python" (or "Open with" > Python).

---

Note: This project is a Work in Progress (WIP).
