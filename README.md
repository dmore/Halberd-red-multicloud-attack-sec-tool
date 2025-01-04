# Halberd: Multi-Cloud Security Testing Tool 🛡️

<p align="center">
  <img src="assets/halberd_logo_banner.jpg" alt="logo" width="100%" align="center"/>
</p>

Halberd is a powerful multi-cloud security testing tool. It is a unified easy-to-use tool, that enables you to execute a comprehensive array of attack techniques across Entra ID, M365, Azure, AWS and GCP. With its intuitive web interface, you can emulate real-world attacks, generate valuable telemetry, and validate your security controls with ease & speed.

## What's the big deal? 🤔

Halberd lets you:

- Execute attack techniques faster than you can say "cloud misconfiguration"
- Generate telemetry that'll make your SOC team beam with joy
- Validate your defenses across Entra ID, M365, Azure, AWS and GCP
- Do it all through a slick web interface that won't make your eyes bleed

<p align="center">
  <img src="assets/halberd_attack_view_v2_0.png" width=100% align="center"/>
</p>

## Getting Started: 0 to Testing in 5 Minutes ⏱️

1. Clone that repo:
   ```
   git clone https://github.com/vectra-ai-research/Halberd.git
   ```

2. Set up your playground:
   ```
   cd Halberd
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Install Azure CLI:
   - Windows: [Official Microsoft guide](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-windows?tabs=azure-cli)
   - Linux: `curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash`
   - macOS: `brew update && brew install azure-cli`

4. Launch Halberd server:
   ```
   python3 run.py
   ```

5. Open `http://127.0.0.1:8050/` in your browser and start testing

   ```
   Additional Server Options
   # Custom Host & Port
   python3 run.py --host 0.0.0.0 --port 8050

   # Enable SSL (HTTPS)
   python3 run.py --ssl-cert /path/to/cert.pem --ssl-key /path/to/key.pem

   # Set Custom Log Level
   python3 run.py --log-level debug

   # Development Server with Debug Mode
   python3 run.py --dev-server --dev-server-debug
   ```

## Using Halberd: Choose Your Own Adventure 🗺️
 
1. **Attack**: Pick your poison – surface, tactic, technique – and start your testing! 
- **Access Manager**: Manage your tokens and sessions like a digital locksmith.
2. **Recon**: Gather intel with visual dashboards. Try the "Entity Map" for a nice visualization!
3. **Automator**: Chain attacks together like a mastermind.
4. **Analyse**: Review your handwork and generate reports.

Checkout [usage](https://github.com/vectra-ai-research/Halberd/wiki/Usage) for more information on testing with Halberd. 

Pro tip: Start with "Initial Access" technique under an attack surface. You can't hack what you can't reach!

## Features that make Halberd awesome! 😮

- 🎭 Realistic attack simulations across multiple cloud platforms
- 🧠 Smart recon dashboards for gathering intel like a pro
- 🎬 Attack playbooks to channel your inner hacker
- 📊 Insightful reports to impress your boss (or your cat)
- 🖥️ CLI access for when you're feeling extra geeky

## Want to Join the Party? 🎉

Got ideas? Found a bug? Want to add that one cool feature? Check out the [contribution guidelines](https://github.com/vectra-ai-research/Halberd/wiki/Contributions) and let's make Halberd even more awesome together.

## Who's Behind This Madness? 🕵️‍♂️

Halberd is the brainchild of [Arpan Sarkar](https://www.linkedin.com/in/arpan-sarkar/)

## Standing on the Shoulders of Giants 🏔️

We didn't reinvent the wheel – we just made it roll smoother. Check out our [inspirations](https://github.com/vectra-ai-research/Halberd/wiki/Additional-(Amazing)-Resources) and show some love to the amazing security tools that paved the way.

Now go forth and hack responsibly! 🚀