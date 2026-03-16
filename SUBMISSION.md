# Submission Package — Varsity Ad Engine

Use this checklist to prepare the final submission (PR7 task 7.5).

---

## Required

1. **GitHub repo URL**  
   - [ ] Add your repo URL here: `https://github.com/<yourname>/AutonomousAdEngine` (or actual repo name)

2. **Streamlit app URL**  
   - [ ] Add your deployed app URL: `https://[yourname]-varsity-ad-engine.streamlit.app`  
   - (Deployment done per 7.3)

3. **Demo video**  
   - [ ] Link to screen recording of Streamlit run (e.g. Loom, YouTube unlisted, or file in repo)  
   - (Recording done per 7.4)

---

## Optional fallback (recommended)

If the Streamlit app sleeps on free tier, reviewers can still verify outputs from the repo.

4. **Representative output run**  
   - [ ] Commit one run from `output/runs/` (e.g. `output/runs/YYYYMMDD_HHMMSS/`) so the repo contains:
     - `ads_library.json`
     - `iteration_log.csv`
     - `quality_trends.png`
     - `images/` (sample PNGs for passing ads)
   - Or commit the latest `output/ads_library.json` and `output/quality_trends.png` plus one run folder.
   - Ensure no secrets or PII are in committed files.

**Example (run from repo root):**

```bash
# Optional: add one run for fallback (replace with your run id)
git add output/runs/20260315_170744/ads_library.json
git add output/runs/20260315_170744/iteration_log.csv
git add output/runs/20260315_170744/quality_trends.png
# Add a few sample images if desired (or skip if .gitignore excludes output/)
git add output/runs/20260315_170744/images/
git commit -m "Add representative pipeline run for submission fallback"
```

If `output/` or `output/runs/` is in `.gitignore`, you may need to force-add or adjust gitignore for the submission branch so reviewers can see a sample run.

---

## Submit

Send to the evaluation channel or submission form:

- **Repo:** \<your GitHub URL\>
- **App:** \<your Streamlit URL\>
- **Demo video:** \<link or attachment\>
