# Ben's Thoughts

For human editing only



## Tasks
1. Sim window needs numbers on icons
2. Logging prints need to be prefixed by type and name (e.g. "[Frontseater] 'interface' web interface at http://127.0.0.1:8765" should start with [Frontseater-interface-0] or something like that)
3. Need live mode for mission push knowledge keys, and needs a way to import from rich editors


## Organization
1. Fix MTOFR package being combined with simulator, and repo being a bit mixed up (toml out of place?)
2. Need to revamp user implementation... more like a ROS node, versus all the amount of code needed for a simple frontseater (start by writing a md checklist of what is needed to implement a new capability and a new platform, then we can work to streamline)
3. Pull each specific knowledge type into a different file, so it is easy to manage the library
4. Scenarios should define the scenario before the mission graphs?  Hmm... I guess the full scenario requires the missions so that's not possible.  Maybe define the vehicles, then the graphs, then the scenario.  Just so it's easier to read.
5. We should have a markdown index somewhere, describing where files are located



## UI
1. Shorthand for UI: interrupts, always-on capabilities, submissions
2. Light mode dark mode?



## Future TODO
1. Make type registry discovery automatic


