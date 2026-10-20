# NSDDD v4.0 — National Security Documents Search

> **Pre-release:** NSDDD 4.0 is a pre-release. The full dataset will be released on Edinburgh DataShare early in the new year, with all the new documents from 2026 plus other additions as they are found; bug fixes are published as updates until then. The installer downloads its data from this project's GitHub release (`data-4.0-pre`), not from DataShare. The DataShare link and citation below refer to 3.5 and will be replaced for the final release. The standalone Windows package runs offline. New users should start with `start_here.html`.

Local semantic search across the [National Security and Defence Documents Dataset (NSDDD) v4.0](https://datashare.ed.ac.uk/handle/10283/9182): **835 national security strategy documents from 125 countries, 1987–2026**, with about 1.38 million pre-computed sentence embeddings in English and 38 original languages. You can search in English or in any of those languages, and look up exact terms in the original texts with keyword search.

Search by concept, filter by country, region, organisation, year, and more — entirely offline after installation.

> **User guide:** The NSDDD 4.0 topic-search guide, [NSDDD_Topic_Search_guide_v4.0.pdf](NSDDD_Topic_Search_guide_v4.0.pdf), covers the search settings, keyword and Boolean search, clustering, social-scientific search strategies, and using NSDDD with an AI assistant through the MCP (which offers semantic, keyword and Boolean search).

---

## Requirements

| | Minimum | Recommended |
|---|---|---|
| RAM | 8 GB | 16 GB |
| Free disk space | 8 GB | 15 GB |
| Storage | SSD strongly advised | SSD |
| Processor | Any 64-bit Intel/AMD or Apple Silicon (about 2018 or later) | Apple M-series, or a recent Intel/AMD with 8+ cores |
| Graphics card | Not needed | Not needed |
| Operating system | macOS 12+ (Apple silicon or Intel), x64 Windows 10/11, or 64-bit Linux | |
| Python | 3.11 or 3.12 (64-bit) | 3.12 |

**Why 8 GB of RAM?** The search app itself peaks at about 3 GB: the language model (Qwen3-Embedding-0.6B, about 1.1 GB), the search index (0.6 GB) and working memory. Segment texts are read from disk as needed rather than held in memory. The operating system, the search interface and your browser come on top, so 8 GB is the practical minimum; 16 GB keeps it fast alongside other work. 4 GB computers are not recommended.

**Why 8 GB of disk?** The installed files take about 4 GB (search index 0.6 GB, segment texts 0.4 GB, language model 1.1 GB, document viewer pages 0.5 GB, Python environment 1–2 GB). During installation the downloaded zip files sit alongside the unpacked files.

**Counting passages:** the corpus holds each translated document in English and in its original language, and both can match a search. By default each passage counts once: an original-language match is merged into the English match of the same passage (the English row also carries the original text). The results banner, the export's Search settings sheet and the MCP field `pairs_merged` say how many were merged. Untick *Count each passage once* to count both.

**Speed:** depends on processor, storage and the number of results. The search page loads the data and the encoder when it opens (up to a minute), so every semantic search is fast, the first included. In Low Power mode the encoder loads on the first semantic search instead. Keyword and Boolean searches use SQLite and never need the encoder.

---

## Installation

### Before you start

**Opening a terminal**

You will need to open a terminal (command line) to check your Python version and run the installer.

- **Mac:** Press `Cmd + Space`, type "Terminal", then press Enter. Or open **Applications > Utilities > Terminal**.
- **Windows:** Click the Start menu, type "Terminal" or "Command Prompt", then press Enter.

---

**Do you have Python 3.11 or 3.12?** (On a Mac you can skip this: `Install NSDDD.command` in Step 3 fetches Python itself if needed.)
Most Macs do. Windows often does not. To check, open a terminal (see above) and type:

```
python3 --version
```

If you see `Python 3.11` or `Python 3.12`, you're ready. If not (or if the command isn't found), install Python from https://www.python.org/downloads/ — on Windows, tick **Add Python to PATH** during install.

**Windows note**

This build uses pinned dependencies for Python 3.11/3.12; Python 3.12 is tested. If you need to install Python, choose Python 3.12 from https://www.python.org/downloads/ — tick **Add Python to PATH** during install.
---

### Step 1 — Download the installer

Click the green **Code** button on this page, then **Download ZIP**. Extract the ZIP — GitHub will usually create a folder called `NSDDD_v4.0_installer-main`.

---

### Step 2 — Open a terminal in that folder

After extracting the ZIP, right-click the extracted installer folder and open a terminal there.

- **Mac:** choose **Open in Terminal**, **New Terminal at Folder**, or **New Terminal Tab at Folder**.
- On some Macs, these options appear inside the **Services** submenu.
- **Windows:** choose **Open in Terminal**.
- **If you do not see that option:** open the extracted folder first, then open a terminal in that exact folder before running the installer.

---

### Step 3 — Run the installer

| Platform | Command |
|---|---|
| **Mac** | Double-click **`Install NSDDD.command`** (no terminal or Python needed: if the Mac has no Python 3.11 or 3.12 it fetches a private copy into the hidden folder `.nsddd_python`, after checking the download against its published checksum) |
| **Linux** | `python3 install.py` |
| **Windows** | `python install.py` |

When prompted for the install directory, press Enter to accept the default location, or type a different path and press Enter.

The installer will walk you through:

- Setting up an isolated Python environment (nothing changed system-wide)
- Downloading the search index and the multilingual language model (Qwen3-Embedding-0.6B) from the project's GitHub data release (about 2.5 GB in total; nothing is downloaded from HuggingFace or Edinburgh DataShare)
- Installing Python dependencies

**Estimated time: 20–45 minutes** depending on internet speed. Downloads can be interrupted and resumed.

---

### Step 4 — Launch

| Platform | How |
|---|---|
| **Mac** | Double-click `Launch.command` in the installer folder |
| **Windows** | Double-click `Launch.vbs` in the installer folder |
| **Terminal (Mac / Linux)** | `python3 launch.py` |
| **Terminal (Windows)** | `python launch.py` |

Your browser opens at `http://localhost:8867`. The search interface loads automatically.

If `Launch.command` (Mac) or `Launch.vbs` (Windows) do not work, open a terminal in the installer folder and run `python3 launch.py` (Mac) or `python launch.py` (Windows) instead.

The same applies to `Install NSDDD.command`. If macOS says `"Launch.command" Not Opened` because Apple could not verify it, open **System Settings > Privacy & Security**, scroll to the security message about `Launch.command`, click **Open Anyway**, then run it again. If needed, you can also Control-click `Launch.command`, choose **Open**, then confirm.

> On startup, the launcher checks for installer updates before opening the interface.

> The browser may briefly show "server not found" for a few seconds while Voilà starts.

---

## Cluster headings

Search results are grouped into clusters, numbered by size (Cluster 1 is the largest). Press **Add AI headings** above the results and a small local language model
(Qwen3-0.6B, 4-bit, 522 MB) reads the six most central distinct sentences of each cluster and writes a 2 to 8 word
heading. Headings never name a country or nationality, are never in capitals, and are never repeated within a search;
the rules are listed at the top of `_library/cluster_labeller.py`; a cluster the model cannot name
keeps its number. It runs on your own computer (about 0.1 s per cluster; about 1 GB more memory during a search).

It needs the optional `llama-cpp-python` package and the file `model/label_model/qwen3-0.6b-q4_k_m.gguf`. If either
is missing, the 'Add AI headings' button is switched off and clusters stay numbered. You can also request headings during a search with the checkbox. Heading generation has a time budget; unfinished clusters keep their numbers, and the native model is released afterwards.

## Updates

**New documents and data** are delivered as a *data version* on the `data-4.0-pre` GitHub release. At start-up (and in `--update-only`) the launcher compares it with the installed data and downloads only the zips that changed, checks their SHA-256, and swaps them in only when all are complete; `NSDDD_AUTO_DATA_UPDATE=0` announces without installing, and `--no-data-update` skips the check for one run. The editor publishes a version with `python publish_data_release.py` (see its docstring); the code-side `document_metadata_4.0.csv` and `VERSION` are published in the usual way.

While NSDDD 4.0 is a pre-release, bug fixes are published often. A download install (the Windows package, or a Mac install from the GitHub zip) **checks for a newer version every time you start it while online, installs it, and tells you** in the launcher window and in a green box on the search page. Offline, it starts the version you have.

```bash
python3 launch.py --update-only   # check and install without starting the search page (Update NSDDD.bat / Update NSDDD.command)
python3 launch.py --no-update     # skip the check for one run
```

- **Download/ZIP installs:** compares the local `VERSION` with the one on GitHub; if newer, downloads the latest files and overlays them while preserving local data folders (`NSDDD_v4.0_workspace`, `outputs`, `.venv`, `data`, etc.). Updates replace program files only; if a release ever needs new packages or data, its notes say so.
- **Git installs (cloned repo):** also update themselves at start-up (a fast-forward `git pull`), but only while no tracked file has local changes and your checkout is not ahead of origin. A checkout with edits only announces the update; run `python3 launch.py --update` to pull it yourself.
- Set `NSDDD_AUTO_UPDATE=0` to stop all automatic installs (program and data), or `NSDDD_AUTO_UPDATE=1` to force them in a git checkout that has local changes.

## Anonymous start-up count

So the project can see roughly how many installs are in use, NSDDD sends **one tiny request a day** when it starts, to the project's free [GoatCounter](https://www.goatcounter.com) page. It carries only the app version, the data version and your operating system family (Windows, macOS or Linux). It sends no documents, searches, names, e-mail addresses or file paths, and sets no cookie. As with any web request, GoatCounter receives the IP address and keeps only a one-way hash of it to tell visitors apart. Offline, nothing is sent, and a failure never stops NSDDD starting. A git checkout never sends it.

To switch it off, set `NSDDD_NO_PING=1` in your environment, or create an empty file called `no_ping` next to `launch.py`. The code is in `usage_ping.py`.

## Search Interface

The browser-based interface provides:

**Two search modes:**
- **Semantic search** — AI-powered conceptual matching (finds documents about an idea, not just exact words)
- **Keyword search** — regex-based, with optional Boolean operators (AND, OR, NOT) and fuzzy matching

**Filters:**
- Country (all 125, individually selectable)
- UN region and subregion
- International organisations (NATO, EU, ASEAN, AU, G7, G20, BRICS, Commonwealth, and more)
- Income group (World Bank classification)
- Democracy status (Freedom House)
- Document type (national security strategy, defence white paper, strategic review)
- Year range (1987–2025)
- Most recent document per country only

**Output:**
- Results grouped into semantic clusters with auto-generated labels
- Export to CSV
- Visualisations: results by year, top countries, cluster overview

---

## Dataset

| | |
|---|---|
| Documents | 835 |
| Countries | 125 |
| Coverage | 1987–2026 |
| Segments | about 1.38 million sentence-level (English for every document, plus the original language for 233 documents) |
| Embedding model | `Qwen/Qwen3-Embedding-0.6B` (multilingual; 256 dimensions, float16; chosen in a 2026 comparison of eight models) |
| Languages | English + translations for 80+ countries |
| DataShare | https://datashare.ed.ac.uk/handle/10283/9182 |

Document types included: national security strategies (NSS), defence white papers (WP), Defence Documents (DD), and Threat Assessments (TA).

---

## Advanced Use

For scripting, custom analysis, or direct access to the notebook:

```bash
jupyter notebook document_metadata_search_voila.ipynb
```

This is the same interface without the browser launcher. Use it if you want to modify the search logic, access results programmatically, or integrate with other notebooks.

To verify your installation or diagnose issues, run:

```bash
python3 verify_install.py      # Windows: python verify_install.py
```

---

## Citation

The following is the existing NSDDD 3.5 citation, pending publication of the 4.0 record:

> Neal, A. W., & Gardner, R. B. (2026). *National Security and Defence Documents Dataset (1987–2025) v3.5*. University of Edinburgh. Edinburgh DataShare. https://datashare.ed.ac.uk/handle/10283/9182

```bibtex
@dataset{neal_gardner_2026_nsddd_v3.5,
  author      = {Neal, Andrew W. and Gardner, Roy B.},
  title       = {National Security and Defence Documents Dataset (1987--2025) v3.5},
  year        = {2026},
  publisher   = {Edinburgh DataShare},
  institution = {University of Edinburgh},
  url         = {https://datashare.ed.ac.uk/handle/10283/9182}
}
```

---

## Troubleshooting

**`python3` not found**
Install Python 3.11 or 3.12 from https://www.python.org/downloads/ (tick "Add to PATH" on Windows).

**Windows semantic search says the encoder is not loaded**
This is usually an environment problem. Delete the local `.venv` folder and run `python install.py` again. If the problem persists, use 64-bit Python 3.11 or 3.12. Python 3.12 is tested.

**Windows says it cannot open `install.py`**
This usually means Terminal or Command Prompt was opened in the wrong folder, often `C:\Windows\System32`. The easiest fix is to close that window, go back to the extracted installer folder, right-click that folder, choose **Open in Terminal**, then run:

```bat
python install.py
```

If the extracted ZIP created a nested folder with the same name, open the inner folder that actually contains `install.py`.

**`permission denied` after dragging the folder into Terminal (Mac)**
This usually means the folder path was pasted on its own, so Terminal tried to run the folder as a program. The easiest fix is to right-click the extracted folder and choose **Open in Terminal**. If needed, use:

```bash
cd /path/to/NSDDD_v4.0_installer-main
```

or type `cd ` first, then drag the folder in and press Enter.

**`"Launch.command" Not Opened` on Mac**
This is usually macOS Gatekeeper blocking a file downloaded from the internet. To allow it:

1. Try opening `Launch.command` once.
2. Open **System Settings > Privacy & Security**.
3. Scroll down to the message saying `Launch.command` was blocked.
4. Click **Open Anyway**.
5. Run `Launch.command` again.

If that still does not work, Control-click `Launch.command`, choose **Open**, then confirm.

**Loading message doesn't clear / interface doesn't appear**
Wait briefly after launch. The server can take a few seconds to start. If needed, close the tab, wait 10 seconds, and reopen `http://localhost:8867`.

**Multiple browser tabs open / interface freezes**
Each launch starts a fresh server; old sessions are stopped automatically. If you experience freezing, close all browser tabs, wait 10 seconds, and reopen `http://localhost:8867`.

**FileNotFoundError during installation**
Check your internet connection. Re-run the installer command for your platform — downloads resume automatically.

**Memory error when loading**
Close other applications. 8 GB of RAM is the minimum; 16 GB is recommended for comfortable use.

**Other issues**
Open an issue at https://github.com/andrewneal78/NSDDD_v4.0_installer/issues or email andrew.neal@ed.ac.uk

---

## License

The installer code (this repository) is released under the **MIT License**.
The NSDDD dataset is released under **CC-BY 4.0**.
The documents in NSDDD are official government publications in the public domain.

## Lower resource use

Run `python launch.py --low-power` (use `python3` on macOS/Linux), or set `NSDDD_LOW_POWER=1` before launching. Set this during source installation to omit the optional AI-heading download/runtime too. This uses two CPU threads and starts with charts and automatic exports switched off. Tick the desired chart/export options and press **Update charts and exports** to generate them for existing results without another search.

The encoder loads when the page opens (in Low Power mode, on the first semantic search). Keyword/Boolean search needs substantially less memory, so Low Power mode suits computers that mostly use it. Keep one browser search session open: each additional Voilà session has its own kernel and can load another model. The optional MCP server preloads its encoder because loading it inside a Windows tool worker previously hung; running MCP and Voilà together also consumes additional memory.

Search scores, thresholds and hits are unchanged by low-power mode. Searches above 6,000 results (3,000 in low-power mode) skip Ward clustering to avoid quadratic memory growth; all hits remain in the results and exports. `NSDDD_CLUSTER_LIMIT` overrides that limit; increasing it requires more RAM. `NSDDD_THREADS` sets a positive processor thread count. Broad searches can still take time to read and export all their results.

Core dependencies are pinned in `requirements.txt`, with transitive release versions in `constraints.txt`. MCP and the HTTP API are optional: install `requirements-mcp.txt` or `requirements-api.txt` only when using those integrations. AI headings use the optional runtime and GGUF model; their absence does not prevent installation. Fuzzy keyword matching uses `rapidfuzz` (installed with the app); it is switched off if that package is missing.

Setup generates missing document viewers from the installed texts, validates index sizes, every SQLite row mapping and metadata IDs, then runs real keyword and semantic searches before announcing success. `python verify_install.py --keyword-only` checks installations that deliberately omit the semantic encoder. Windows setup includes the Microsoft VC++ x64 redistributable and may request administrator consent or a reboot.

The main test host is Apple silicon macOS with Python 3.12; the offline Windows wheel set targets x64 Python 3.12 and was tested on a Windows 11 laptop and in a Windows 11 ARM virtual machine (x64 emulation) on an Apple M4 Max. **Intel Macs** get PyTorch 2.2.2 automatically (PyTorch 2.9 has no Intel-Mac build); in a test on an emulated Intel Mac the same search returned the identical 566 results and 8 clusters as on Apple silicon, with scores within 0.002. AI headings are not available on Intel Macs. Windows on ARM and 32-bit systems are not supported (PyTorch has no build for them at this version). If port 8867 is occupied, the launcher chooses another free port and prints the actual address. Export links use that address and require the corresponding server to remain running.
