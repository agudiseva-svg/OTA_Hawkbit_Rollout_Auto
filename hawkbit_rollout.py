#!/usr/bin/env python3
"""
Hawkbit Config-Driven Rollout Script
------------------------------------
- Reads rollout settings from config.json
- Supports multiple firmware sequences (e.g., "1.0", "1.1", "0.9")
- Looks up distribution sets dynamically by name and version
- Creates target filters and rollouts for each DS
- Starts and monitors rollout progress continuously
- Checks installed/assigned DS versions per target
"""

import os
import csv
import time
import json
import requests
from pathlib import Path

CONFIG_FILE = "config.json"
CSV_FILE = "target_rollout.csv"
FILTER_NAME = "Target_filter"
ROLLOUT_PREFIX = "Rollout_Seq"

# ----------------------------------------------------------------------
# Method: load_config()
# Purpose:
#     Load the Hawkbit rollout configuration from a JSON file.
# Parameters:
#     path - Path to configuration file
# Created by:  Adi Gudiseva
# Date:        10.23.2025
# ----------------------------------------------------------------------
def load_config(path):
    if not Path(path).exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r") as f:
        cfg = json.load(f)
    return cfg


# ----------------------------------------------------------------------
# Method: init_session()
# Purpose:
#     Initialize a persistent HTTP session for Hawkbit API calls.
# Parameters:
#     url - Hawkbit server URL
#     user - Username
#     pw - Password
# Created by:  Adi Gudiseva
# Date:        10.23.2025
# ----------------------------------------------------------------------
def init_session(url, user, pw):
    s = requests.Session()
    s.auth = (user, pw)
    s.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json"
    })
    s.base_url = url
    return s


# ----------------------------------------------------------------------
# Method: get_distribution_set()
# Purpose:
#     Find a distribution set ID by exact name and version.
# Parameters:
#     session - Active Hawkbit session
#     name - Distribution set name
#     version - Distribution set version
# Created by:  Adi Gudiseva
# Date:        10.23.2025
# ----------------------------------------------------------------------
def get_distribution_set(session, name, version):
    url = f"{session.base_url}/rest/v1/distributionsets?name=={name};version=={version}"
    r = session.get(url)
    if r.status_code != 200:
        print(f"Failed to query distribution set: HTTP {r.status_code}")
        return None

    data = r.json()
    sets = data.get("content") or data.get("_embedded", {}).get("distributionsets", [])
    for ds in sets:
        if ds.get("name") == name and ds.get("version") == version:
            print(f"Found distribution set: {name} ({version}) → ID={ds.get('id')}")
            return ds.get("id")

    print(f"Distribution set '{name}' ({version}) not found (exact match).")
    return None


# ----------------------------------------------------------------------
# Method: generate_or_query()
# Purpose:
#     Build an RSQL query string from a CSV file of serial numbers.
# Parameters:
#     csv_file - Path to CSV file containing serial numbers
# Created by:  Adi Gudiseva
# Date:        10.23.2025
# ----------------------------------------------------------------------
def generate_or_query(csv_file):
    serials = []
    with open(csv_file, newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            for val in row:
                val = val.strip()
                if val:
                    serials.append(val)
    if not serials:
        raise RuntimeError("CSV empty or unreadable.")
    return "(" + " or ".join([f'name==\"{s}\"' for s in serials]) + ")", serials


# ----------------------------------------------------------------------
# Method: create_target_filter()
# Purpose:
#     Create or update a target filter in Hawkbit.
# Parameters:
#     session - Active Hawkbit session
#     name - Filter name
#     query - Filter RSQL query
# Created by:  Adi Gudiseva
# Date:        10.23.2025
# ----------------------------------------------------------------------
def create_target_filter(session, name, query):
    url = f"{session.base_url}/rest/v1/targetfilters"
    payload = {"name": name, "query": query}

    r = session.post(url, json=payload)
    if r.status_code in (200, 201):
        print(f"Filter '{name}' created.")
        return True
    elif r.status_code == 409:
        print(f"Filter '{name}' exists, updating...")
        resp = session.get(url)
        data = resp.json()
        filters = data.get("content") or data.get("_embedded", {}).get("targetfilters", [])
        fid = next((f.get("id") for f in filters if f.get("name") == name), None)
        if fid:
            u = session.put(f"{url}/{fid}", json=payload)
            if u.status_code in (200, 204):
                print("Updated existing filter.")
                return True
            else:
                print(f"Update failed {u.status_code}: {u.text}")
        else:
            print("Filter ID not found during update.")
        return False
    else:
        print(f"Filter creation failed: HTTP {r.status_code} → {r.text}")
        return False


# ----------------------------------------------------------------------
# Method: create_rollout()
# Purpose:
#     Create a rollout for a given distribution set and target filter.
# Parameters:
#     session - Active Hawkbit session
#     name - Rollout name
#     query - Target filter query
#     ds_id - Distribution set ID
#     group_size - Number of rollout groups
#     action_type - Type of rollout action
# Created by:  Adi Gudiseva
# Date:        10.23.2025
# ----------------------------------------------------------------------
def create_rollout(session, name, query, ds_id, group_size, action_type):
    url = f"{session.base_url}/rest/v1/rollouts"
    payload = {
        "name": name,
        "distributionSetId": ds_id,
        "targetFilterQuery": query,
        "actionType": action_type,
        "amountGroups": group_size,
        "start": "auto"
    }
    print("Payload:", json.dumps(payload, indent=2))
    r = session.post(url, json=payload)

    if r.status_code in (200, 201):
        data = r.json()
        rid = data.get("id")
        print(f"Rollout '{name}' created (ID={rid}).")
        return rid
    elif r.status_code == 409:
        print(f"Rollout '{name}' already exists — skipping creation.")
        return None
    else:
        print(f"Rollout creation failed: {r.status_code} → {r.text}")
        return None


# ----------------------------------------------------------------------
# Method: start_rollout()
# Purpose:
#     Wait until rollout is ready and start it automatically.
# Parameters:
#     session - Active Hawkbit session
#     rollout_id - ID of the rollout to start
# Created by:  Adi Gudiseva
# Date:        10.23.2025
# ----------------------------------------------------------------------
def start_rollout(session, rollout_id):
    if not rollout_id:
        return
    rollout_url = f"{session.base_url}/rest/v1/rollouts/{rollout_id}"
    for attempt in range(20):
        r = session.get(rollout_url)
        if r.status_code == 200:
            state = r.json().get("status")
            print(f"Rollout status: {state}")
            if state == "ready":
                break
        time.sleep(5)
    else:
        print("Timeout waiting for rollout to become ready.")
        return

    start_url = f"{rollout_url}/start"
    r = session.post(start_url)
    if r.status_code in (200, 202):
        print(f"Rollout ID {rollout_id} started successfully.")
    else:
        print(f"Failed to start rollout: {r.status_code} → {r.text}")


# ----------------------------------------------------------------------
# Method: monitor_rollout_until_done()
# Purpose:
#     Monitor rollout progress continuously until finished or timeout.
# Parameters:
#     session - Active Hawkbit session
#     rollout_id - Rollout ID
#     interval - Polling interval in seconds
#     timeout - Timeout duration in seconds
# Created by:  Adi Gudiseva
# Date:        10.23.2025
# ----------------------------------------------------------------------
def monitor_rollout_until_done(session, rollout_id, interval=10, timeout=1800):
    print("\nMonitoring rollout progress (Ctrl+C to stop)...\n")
    rollout_url = f"{session.base_url}/rest/v1/rollouts/{rollout_id}"
    start_time = time.time()

    try:
        while True:
            r = session.get(rollout_url)
            if r.status_code != 200:
                print(f"Failed to fetch progress: {r.status_code}")
                time.sleep(interval)
                continue

            data = r.json()
            status = data.get("status")
            total = data.get("totalTargets", 0)
            done = data.get("totalTargetsCompleted", 0)
            failed = data.get("totalTargetsFailed", 0)
            pending = data.get("totalTargetsPending", 0)
            print(f"Status: {status} | Completed: {done} | Failed: {failed} | Pending: {pending} | Total: {total}")

            if status in ["finished", "error", "paused"]:
                print(f"\nRollout ended with status: {status.upper()}")
                break

            if time.time() - start_time > timeout:
                print("Timeout reached. Stopping monitoring.")
                break

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\nMonitoring stopped by user.")


# ----------------------------------------------------------------------
# Method: get_assigned_ds()
# Purpose:
#     Fetch assigned Distribution Set for a specific target.
# Parameters:
#     session - Active Hawkbit session
#     target_id - Target ID
# Created by:  Adi Gudiseva
# Date:        10.23.2025
# ----------------------------------------------------------------------
def get_assigned_ds(session, target_id):
    url = f"{session.base_url}/rest/v1/targets/{target_id}/assignedDS"
    r = session.get(url)
    if r.status_code == 200:
        ds = r.json()
        print(f"Assigned: {ds.get('name')} ({ds.get('version')})")
        return True
    elif r.status_code == 204:
        print("No assigned distribution set.")
        return False
    else:
        print(f"Error fetching assigned DS: HTTP {r.status_code}")
        return False


# ----------------------------------------------------------------------
# Method: get_installed_ds()
# Purpose:
#     Fetch the installed Distribution Set for a specific target.
# Parameters:
#     session - Active Hawkbit session
#     target_id - Target ID
# Created by:  Adi Gudiseva
# Date:        10.23.2025
# ----------------------------------------------------------------------
def get_installed_ds(session, target_id):
    url = f"{session.base_url}/rest/v1/targets/{target_id}/installedDS"
    r = session.get(url)
    if r.status_code == 200:
        ds = r.json()
        print(f"Installed: {ds.get('name')} ({ds.get('version')})")
        return True
    elif r.status_code == 204:
        print("No installed DS found, continuing rollout...")
        return False
    else:
        print(f"Error fetching installed DS: HTTP {r.status_code}")
        return False

# ----------------------------------------------------------------------
# Method: get_firmware_history()
# Purpose:
#     Retrieve and display the full firmware rollout history (Actions)
#     for a given target. This includes all previously installed
#     Distribution Sets, not just the latest assigned or installed DS.
# Parameters:
#     session - Active Hawkbit session
#     target_id - Target ID (serial number)
# Created by:  Adi Gudiseva
# Date:        10.24.2025
# ----------------------------------------------------------------------
def get_firmware_history(session, target_id):
    url = f"{session.base_url}/rest/v1/targets/{target_id}/actions"
    r = session.get(url)

    if r.status_code != 200:
        print(f"Error fetching firmware history: HTTP {r.status_code}")
        return

    actions = r.json().get("content", [])
    if not actions:
        print("No firmware history found.")
        return

    print(f"\nFirmware History for Target: {target_id}")
    print("-" * 50)
    for act in actions:
        ds = act.get("distributionSet", {})
        ds_name = ds.get("name", "Unknown")
        ds_version = ds.get("version", "N/A")
        exec_status = act.get("status", {}).get("execution", "N/A")
        start_time = act.get("createdAt", "N/A")
        print(f"{ds_name} ({ds_version}) - {exec_status} | Started: {start_time}")
    print("-" * 50)

# ----------------------------------------------------------------------
# Method: main()
# Purpose:
#     Entry point for Hawkbit rollout process using configuration file.
# Parameters:
#     None
# Created by:  Adi Gudiseva
# Date:        10.23.2025
# ----------------------------------------------------------------------
def main():
    config = load_config(CONFIG_FILE)
    url = config["hawkbit"]["url"]
    user = config["hawkbit"]["username"]
    pw = config["hawkbit"]["password"]
    session = init_session(url, user, pw)
    poll_interval = config["polling"]["interval"]
    poll_timeout = config["polling"]["timeout"]

    print("\nAvailable firmware sequences:")
    for seq in config["sequences"]:
        print(f"  - {seq}")
    seq_choice = input("\nEnter sequence version to deploy (e.g. 1.1): ").strip()
    if seq_choice not in config["sequences"]:
        print(f"Invalid sequence '{seq_choice}' — must be one of {list(config['sequences'].keys())}")
        return

    query, serials = generate_or_query(CSV_FILE)
    serial_suffix = serials[0][-5:]  # last 5 chars of first serial
    print(f"\nUsing serial suffix for rollout naming: {serial_suffix}")
    print("Query:", query)
    if not create_target_filter(session, FILTER_NAME, query):
        print("Target filter step failed, aborting.")
        return

    for idx, ds in enumerate(config["sequences"][seq_choice], start=1):
        print(f"\nStarting rollout {idx}/{len(config['sequences'][seq_choice])}: {ds['name']} ({ds['version']})")
        ds_id = get_distribution_set(session, ds["name"], ds["version"])
        if not ds_id:
            print("Skipping rollout — DS not found.")
            continue

        rollout_name = f"{ROLLOUT_PREFIX}_{seq_choice}_{serial_suffix}_{idx}"
        rollout_id = create_rollout(session, rollout_name, query, ds_id, 1, "forced")
        if rollout_id:
            start_rollout(session, rollout_id)
            monitor_rollout_until_done(session, rollout_id, poll_interval, poll_timeout)
        else:
            print(f"Rollout '{rollout_name}' not created.")

    print("\nChecking target versions:\n")
    for target in serials:
        print(f"Target: {target}")
        get_assigned_ds(session, target)
        get_installed_ds(session, target)
        get_firmware_history(session, target)
        print("-" * 50)


if __name__ == "__main__":
    main()
