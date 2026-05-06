# DE1_project_processor

Python scripts for automated processing of VHDL projects

## Cloning repositories

### Get links
Fill in provided `git_links_de1.json` file with links to the repositories.
Structure is provided by the timetable slot (such as `st_10` which stands for Wednesday at 10') and then the numbering is 1-X, that is corresponding to the Excel document.

`st_10` is hereafter called as group and number 1-X is called as subgroup

### Clone
Run `clone_repos.py` and it will clone repositories provided in json file to the corresponding folder structures


## Process projects

For generating reports run following code for processing whole group:

`process.py --vivado "C:\AMDDesignTools\2025.2\Vivado\bin\vivado.bat" --group st_10`

Or you can process only one subgroup (one project):

`process.py --vivado "C:\AMDDesignTools\2025.2\Vivado\bin\vivado.bat" --group st_10 --subgroup 5`

It will find `.xpr` Vivado project file and automatically opens it, if there is more than one project user is informed in terminal with the choice list. Then project is processed and final report in markdown is written in root directory of processed subgroup


## Merging reports
As the generated reports are spread over subgroups folder, there is script for merging them into one HTML with basic formatting and structuring. It will automatically search for all markdown reports available. Just run:

`generate_de1_reports.py`
