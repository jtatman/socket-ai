# Socket-AI IRC Multi-Bot Framework

## Overview
Socket-AI is a powerful framework for running multiple Large-Language-Model-powered IRC bots, each with a distinct personality and area of expertise. Bots are organized into environment-specific teams, making it easy to manage different contexts and conversations.

## Project Structure
```
├── bots/                      # Re-usable bot engine
│   └── irc_bot.py             # Core bot implementation
├── environments/              # One folder per environment/team
│   ├── cantina/               # Star Wars Cantina (fully tested)
│   ├── business_development/  # Business development team
│   ├── dev_ops/               # DevOps specialists
│   ├── philosophy/            # Philosophical discussions
│   ├── marketing/             # Marketing experts
│   ├── saas/                  # SaaS industry specialists
│   ├── product_development/   # Product management
│   └── planning/              # Project planning and strategy
├── logs/                      # Application and test logs
├── prompts/                   # Bot personalities and behaviors
├── scripts/                   # Utility scripts
│   ├── launch_team.py         # Launch environment teams
│   └── launch_bot.py          # Launch individual bots
└── tests/                     # Test suite
    ├── test_irc_bots.py       # Integration tests
    └── test_mock_server.py    # Mock IRC server tests
```

## Available Bot Teams

### 🌌 Star Wars Cantina Team
Fully tested team of iconic Star Wars characters for demonstration and testing.

| Bot | Personality | Description |
|-----|-------------|-------------|
| **R2D2** | The loyal astromech droid | Communicates in beeps and whistles (with translations). Curious, helpful, and occasionally cheeky. |
| **C3PO** | The protocol droid | Speaks formally and politely, offering helpful translations and etiquette advice. |
| **HanSolo** | The scoundrel | Responds with dry wit, occasional sarcasm, and references to the Millennium Falcon. |
| **Chewbacca** | The Wookiee | Communicates in Wookiee growls with translations. Shows loyalty and occasional humor. |
| **PrincessLeia** | The leader | Speaks with confidence and leadership. Offers diplomatic solutions with sharp retorts when needed. |

### 🏢 Business Development Team
Experts in business growth and strategy.

### 🛠️ DevOps Team
Specialists in development operations and infrastructure.

### 🤔 Philosophy Team
For deep discussions and thought experiments.

### 📢 Marketing Team
Creative minds for marketing strategies and campaigns.

### ☁️ SaaS Team
Specialists in software-as-a-service business models.

### 🎯 Product Development
Experts in product management and development.

### 📅 Planning Team
For project planning and strategic initiatives.

## Quick Start

1. **Setup Environment**
   ```bash
   # Create and activate virtual environment (Windows)
   python -m venv .venv
   .\.venv\Scripts\activate
   
   # Install development dependencies
   pip install -r requirements-dev.txt
   
   # Install the package in development mode
   pip install -e .
   ```

2. **Start an IRC Server**
   You can use the included miniircd server for testing:
   ```bash
   # Start miniircd on port 16667 (non-standard port to avoid conflicts)
   python tests/run_miniircd.py --port 16667
   ```
   
   Or use any other IRC server by updating the configuration files accordingly.

3. **Launch Bot Teams**
   ```powershell
   # Launch a single environment
   python scripts/launch_team.py environments/cantina
   
   # Launch with debug logging
   python scripts/launch_team.py --debug environments/cantina
   
   # Launch a specific bot
   python scripts/launch_bot.py --env cantina --bot r2d2
   ```

   Each bot connects using its YAML configuration and listens for messages that mention its nickname or direct messages.

4. **Verify Connection**
   Connect to the IRC server using your favorite IRC client:
   ```
   Server: localhost
   Port: 16667
   Channel: #cantina
   ```
   
   Or use the test client:
   ```bash
   python -m irc.client -s localhost -p 16667 -n TestUser -c '#cantina'
   ```

## Testing

The test suite verifies both the core functionality and integration with the IRC server:

```powershell
# Run all tests
pytest tests/

# Run tests with detailed output
pytest -v --log-cli-level=INFO

# Run a specific test file
pytest tests/test_irc_bots.py -v

# Run a specific test case
pytest tests/test_miniircd_connection.py::TestMiniIRCDConnection::test_connection_and_registration -v

# Run with coverage report
pytest --cov=bot_framework tests/
```

### Test Types
- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test interactions between components
- **End-to-End Tests**: Test the full stack with a real IRC server

## Adding a New Bot

1. **Create a Prompt**
   Add a markdown file at `prompts/<environment>/<BotName>.md` describing the bot's personality and behavior.

2. **Create Configuration**
   Add a YAML configuration file at `environments/<environment>/<BotName>.yml` with the bot's settings. Use existing configurations as examples.

3. **Test Your Bot**
   Launch your new bot and interact with it in your IRC channel:
   ```
   python scripts/launch_bot.py --env <environment> --bot <BotName>
   ```

## Logs
All application logs are stored in the `logs/` directory. Check these files for debugging and monitoring bot activity.

## Contributing
Contributions are welcome! Please follow the existing code style and include tests for new features.
3. Relaunch with `launch_team.py`.

## Configuration Keys (YAML)
* `nick` – IRC nickname.
* `channel` – channel to join.
* `host`, `port`, `tls` – IRC server.
* `model` – LLM backend identifier.
* `temperature` – creativity (0.0-1.0).
* `prompt` – relative path to markdown personality.
* `llm_node` – URL/IP where the proxy is listening.

## Troubleshooting

### Common Issues

#### Connection Issues
- **"Connection refused" errors**: Ensure the IRC server is running and accessible
- **Nickname in use**: The test suite generates unique nicknames, but if you see this, try:
  ```bash
  # Clear any stale connections
  killall miniircd 2>/dev/null || true
  ```

#### Test Failures
- **Timeouts**: Some tests have timeouts that might need adjustment for slower systems
- **Port conflicts**: Ensure port 16667 is available or update the test configuration

### Debugging

Enable debug logging for more detailed output:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Or when running tests:
```bash
LOGLEVEL=DEBUG pytest -v tests/
```

## Maintenance

### Code Quality
- Run `black .` to format code
- Use `flake8` for linting
- Keep docstrings updated using Google style

### Project Structure
- `scripts/`: Utility scripts for development and deployment
- `tests/`: Test suite with unit and integration tests
- `environments/`: Bot configurations organized by team/environment
- `prompts/`: Bot personality and behavior definitions

### Updating Dependencies
```bash
# Update requirements
pip freeze > requirements.txt

# Install updated dependencies
pip install -r requirements.txt
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

MIT License - see the [LICENSE](LICENSE) file for details.
