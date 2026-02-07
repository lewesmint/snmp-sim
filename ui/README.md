# SNMP GUI Controller

A simple tkinter-based GUI application for controlling the SNMP agent's sysDescr value.

## Features

- **Set sysDescr**: Enter a new value and click "Set sysDescr" to update the SNMP agent
- **Get Current Value**: Fetch and display the current sysDescr value from the agent
- **Activity Log**: View all operations and their results in real-time
- **Status Bar**: Shows the current operation status

## Requirements

```bash
pip install requests
```

Note: `tkinter` is included with most Python installations.

## Usage

### 1. Start the SNMP Agent with REST API

First, make sure the SNMP agent with REST API is running:

```bash
python run_agent_with_rest.py
```

This will start:
- SNMP agent on port 11161
- REST API on http://127.0.0.1:6060

### 2. Launch the GUI

```bash
python ui/snmp_gui.py
```

### 3. Using the GUI

1. The application will automatically load the current sysDescr value on startup
2. Enter a new description in the text box
3. Click "Set sysDescr" to update the value
4. Click "Get Current Value" to refresh the displayed value
5. Monitor the activity log for operation results
6. Click "Clear Log" to clear the activity log

## Testing

You can verify the changes using SNMP commands:

```bash
# Get the current sysDescr value
snmpget -v2c -c public localhost:11161 .1.3.6.1.2.1.1.1.0

# Or use snmpwalk
snmpwalk -v2c -c public localhost:11161 .1.3.6.1.2.1.1.1
```

## Architecture

The GUI communicates with the SNMP agent through the REST API:

```
┌─────────────┐      HTTP       ┌──────────────┐      SNMP      ┌──────────┐
│  GUI App    │ ──────────────> │  REST API    │ ────────────> │  SNMP    │
│ (tkinter)   │ <────────────── │ (FastAPI)    │ <──────────── │  Agent   │
└─────────────┘                 └──────────────┘                └──────────┘
```

## API Endpoints Used

- `GET /sysdescr` - Retrieve current sysDescr value
- `POST /sysdescr` - Set new sysDescr value

## Troubleshooting

**"Cannot connect to REST API"**
- Make sure `run_agent_with_rest.py` is running
- Check that the REST API is accessible at http://127.0.0.1:6060
- Try accessing http://127.0.0.1:6060/docs in your browser

**"SNMP agent not initialized"**
- The SNMP agent may still be starting up
- Wait a few seconds and try again

