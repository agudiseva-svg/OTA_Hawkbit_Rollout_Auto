# Hawkbit Config-Driven Rollout Script

### Author: Adi Gudiseva  
**Date:** 10.24.2025  
**Version:** 1.0  

---

##  Overview

This Python script automates **firmware rollouts using the Eclipse Hawkbit REST API**.  
It reads rollout configuration dynamically from a JSON file (`config.json`) and supports multiple firmware sequences such as `1.0`, `1.1`, or `0.9`.

It handles:
- Creation and update of **target filters**
- Automated **rollout creation**, start, and monitoring
- Retrieval of **assigned** and **installed** firmware
- Display of **firmware history** (all previously installed distributions)
- Configurable polling intervals and timeouts

---

##  Features

- **Config-Driven:** Firmware names, versions, and sequences are loaded from `config.json`.
- **Automatic Target Filtering:** Serial numbers in a CSV file define rollout targets.
- **Rollout Monitoring:** Displays live rollout progress until completion.
- **Firmware Verification:** Checks both assigned and installed DS per target.
- **Firmware History:** Lists all previously installed firmware versions from Hawkbit.
- **Clean Logging:** Fully timestamped and consistent with Hawkbit’s REST conventions.

---

##  Requirements
Update versions in config.json file (check from hawkbit)
Update Serial numbers in target_rollout.csv file
Create a Python virtual environment and install dependencies:

```bash
python -m venv venv
cd venv\Scripts\activate            # (Windows)
cd .. (come back to root project folder location)
pip install -r requirements.txt
command:
python hawkbit_deploy.py
Available firmware sequences:
  - 1.0
  - 1.1
Enter sequence version to deploy (e.g. 1.0): 1.0



