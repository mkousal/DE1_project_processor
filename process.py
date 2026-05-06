#!/usr/bin/env python3
"""
Xilinx Vivado 2025.2 FPGA Project Batch Processor

Automates the processing of multiple Vivado projects with comprehensive
error handling, design analysis, and report generation.

Usage:
    python process.py --path D:\\projects
    python process.py --path D:\\projects --group ct_10
    python process.py --path D:\\projects --group ct_10 --non-interactive
    python process.py --path D:\\projects --select "alarm" --verbose
    python process.py --vivado "C:\AMDDesignTools\2025.2\Vivado\bin\vivado.bat" --group ct_8 --subgroup 1
"""

import os
import re
import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple, Dict, Optional

# ============================================================================
# CONFIGURATION
# ============================================================================

VIVADO_TIMEOUT = 600  # 10 minutes

# ============================================================================
# CLI ARGUMENTS
# ============================================================================
def parse_args():
    parser = argparse.ArgumentParser(
        description="Vivado 2025.2 Batch Project Processor",
        epilog="Examples:\n"
               "  %(prog)s --path D:\\projects\n"
               "  %(prog)s --path D:\\projects --group ct_10 --non-interactive\n"
               "  %(prog)s --path D:\\projects --select alarm",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("--path", 
                       help="Root directory (default: current directory)")
    parser.add_argument("--vivado", 
                       default="vivado",
                       help="Vivado executable path (default: vivado)")
    parser.add_argument("--non-interactive", 
                       action="store_true",
                       help="Use first .xpr without prompting")
    parser.add_argument("--select", 
                       help="Pattern to filter .xpr files (substring match)")
    parser.add_argument("--group", 
                       help="Process only specific group folder")
    parser.add_argument("--subgroup", 
                       help="Process only specific subgroup folder")
    parser.add_argument("--verbose", "-v",
                       action="store_true",
                       help="Enable verbose logging")
    parser.add_argument("--keep-temp",
                       action="store_true",
                       help="Keep temporary Tcl scripts")

    return parser.parse_args()


# ============================================================================
# PROJECT DISCOVERY
# ============================================================================

def find_xpr_files(folder: Path) -> List[Path]:
    """Recursively find all .xpr files in a folder."""
    try:
        xprs = sorted(Path(folder).rglob("*.xpr"))
        return xprs
    except Exception as e:
        print(f"    [ERROR] Failed to search for .xpr: {e}")
        return []


def select_xpr(xprs: List[Path], args) -> Optional[Path]:
    """Select a single .xpr file from the list."""
    if not xprs:
        return None

    # Filter by pattern if provided
    if args.select:
        filtered = [x for x in xprs if args.select.lower() in str(x).lower()]
        if filtered:
            xprs = filtered
            if len(xprs) == 1:
                return xprs[0]

    # Non-interactive: use first
    if args.non_interactive or len(xprs) == 1:
        return xprs[0]

    # Interactive: prompt user
    print("    [INFO] Multiple .xpr files found:")
    for i, x in enumerate(xprs, 1):
        rel_path = x.relative_to(x.parent.parent.parent) if len(x.parents) >= 3 else x
        print(f"      [{i}] {rel_path}")
    
    try:
        idx = int(input("    Select project number (1-{}): ".format(len(xprs))))
        if 1 <= idx <= len(xprs):
            return xprs[idx - 1]
    except (ValueError, IndexError):
        pass
    
    print("    [INFO] Invalid selection, using first project")
    return xprs[0]


# ============================================================================
# TCL SCRIPT GENERATION
# ============================================================================

def to_tcl_path(p: Path) -> str:
    """Convert a Python Path to TCL-compatible forward-slash path."""
    return str(p.resolve()).replace("\\", "/")


def generate_tcl_script(xpr_path: Path, tcl_path: Path, verbose: bool = False) -> None:
    """Generate a comprehensive Tcl script for Vivado batch processing."""
    xpr = to_tcl_path(xpr_path)
    
    tcl_content = f'''# Vivado Batch Processing Script
# Generated for: {xpr_path.name}

proc print_separator {{title}} {{
    puts ""
    puts "================================"
    puts "$title"
    puts "================================"
}}

# Configuration
set verbose {1 if verbose else 0}
set proj "{xpr}"
set start_time [clock seconds]

print_separator "PROJECT OPEN"
puts "Project: $proj"

if {{![file exists $proj]}} {{
    puts "ERROR: Project file not found: $proj"
    exit 1
}}

open_project $proj

# Reset and run synthesis
print_separator "SYNTHESIS"
reset_run synth_1
set synth_start [clock seconds]
launch_runs synth_1 -jobs 10
wait_on_run synth_1

if {{[get_property PROGRESS [get_runs synth_1]] eq "100%"}} {{
    if {{[string match "*ERROR*" [get_property STATUS [get_runs synth_1]]]}} {{
        puts "ERROR: Synthesis failed"
    }} else {{
        puts "SUCCESS: Synthesis completed"
    }}
}} else {{
    puts "ERROR: Synthesis did not complete"
}}

# Run implementation
print_separator "IMPLEMENTATION"
reset_run impl_1
set impl_start [clock seconds]
launch_runs impl_1 -to_step write_bitstream -jobs 10
wait_on_run impl_1

if {{[get_property PROGRESS [get_runs impl_1]] eq "100%"}} {{
    if {{[string match "*ERROR*" [get_property STATUS [get_runs impl_1]]]}} {{
        puts "ERROR: Implementation failed"
    }} else {{
        puts "SUCCESS: Implementation completed"
    }}
}} else {{
    puts "ERROR: Implementation did not complete"
}}

# Report synthesis details
print_separator "SYNTHESIS REPORT"
if {{[file exists "[get_property DIRECTORY [current_project]]/[current_project].runs/synth_1/synth_1.rpt"]}} {{
    set synth_rpt [open "[get_property DIRECTORY [current_project]]/[current_project].runs/synth_1/synth_1.rpt" r]
    set synth_content [read $synth_rpt]
    close $synth_rpt
    
    # Extract key metrics
    if {{[regexp {{Number of Slice Registers:\\s+(\\d+)}} $synth_content - registers]}} {{
        puts "  Slice Registers: $registers"
    }}
    if {{[regexp {{Number of Slice LUTs:\\s+(\\d+)}} $synth_content - luts]}} {{
        puts "  Slice LUTs: $luts"
    }}
}}

# Report implementation details  
print_separator "IMPLEMENTATION REPORT"
if {{[file exists "[get_property DIRECTORY [current_project]]/[current_project].runs/impl_1/impl_1.rpt"]}} {{
    set impl_rpt [open "[get_property DIRECTORY [current_project]]/[current_project].runs/impl_1/impl_1.rpt" r]
    set impl_content [read $impl_rpt]
    close $impl_rpt
    
    if {{[regexp {{Slice LUTs \\(excluding route\\):\\s+(\\d+)}} $impl_content - luts]}} {{
        puts "  Slice LUTs (used): $luts"
    }}
}}

# Report timing
print_separator "TIMING INFORMATION"
if {{[file exists "[get_property DIRECTORY [current_project]]/[current_project].runs/impl_1/impl_1_timing_summary_routed.rpt"]}} {{
    catch {{
        set timing_rpt [open "[get_property DIRECTORY [current_project]]/[current_project].runs/impl_1/impl_1_timing_summary_routed.rpt" r]
        while {{[gets $timing_rpt line] >= 0}} {{
            if {{[string match "*WNS*" $line] || [string match "*TNS*" $line]}} {{
                puts "$line"
            }}
        }}
        close $timing_rpt
    }}
}}

# Summary
set end_time [clock seconds]
set elapsed [expr {{$end_time - $start_time}}]

print_separator "SUMMARY"
puts "Total time: $elapsed seconds"
puts "Synthesis Status: [get_property STATUS [get_runs synth_1]]"
puts "Implementation Status: [get_property STATUS [get_runs impl_1]]"

exit 0
'''
    
    tcl_path.write_text(tcl_content)
    if verbose:
        print(f"    [DEBUG] Tcl script generated: {tcl_path}")


# ============================================================================
# VIVADO EXECUTION
# ============================================================================

def run_vivado(vivado_bin: str, tcl_script: Path, cwd: Path, verbose: bool = False) -> Tuple[str, int]:
    """Execute Vivado in batch mode with the given Tcl script."""
    vivado_log = cwd / "vivado_batch.log"
    vivado_jou = cwd / "vivado.jou"
    
    cmd = [
        vivado_bin,
        "-mode", "batch",
        "-source", str(tcl_script),
        "-log", str(vivado_log),
        "-journal", str(vivado_jou),
        "-notrace"
    ]
    
    if verbose:
        print(f"    [DEBUG] Running: {' '.join(cmd)}")
        print(f"    [DEBUG] CWD: {cwd}")
    
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=VIVADO_TIMEOUT
        )
        
        stdout_content = proc.stdout
        
        # Try to read the log file
        if vivado_log.exists():
            try:
                log_content = vivado_log.read_text(errors="ignore")
                stdout_content += "\n--- VIVADO LOG ---\n" + log_content
            except:
                pass
        
        return stdout_content, proc.returncode
        
    except subprocess.TimeoutExpired:
        return f"ERROR: Vivado execution timed out ({VIVADO_TIMEOUT}s)", -1
    except Exception as e:
        return f"ERROR: Failed to execute Vivado: {str(e)}", -1


# ============================================================================
# LOG PARSING & ERROR EXTRACTION
# ============================================================================

def parse_vivado_output(output: str) -> Tuple[List[str], List[str], List[str], bool, bool, bool]:
    """Parse Vivado output and extract errors, warnings, and status."""
    errors = []
    critical_warnings = []
    warnings = []
    
    synth_ok = "synth_1 completed successfully" in output or "SUCCESS: Synthesis completed" in output
    impl_ok = "impl_1 completed successfully" in output or "SUCCESS: Implementation completed" in output
    bitstream_ok = "write_bitstream completed successfully" in output
    
    for line in output.splitlines():
        # Skip specific warnings to ignore
        if "[Board 49-26]" in line:
            continue
        
        # Extract errors
        if re.search(r"\[ERROR\]|\bERROR:", line, re.IGNORECASE):
            line_clean = line.strip()
            if line_clean and line_clean not in errors:
                errors.append(line_clean)
        
        # Extract critical warnings
        elif re.search(r"\[CRITICAL WARNING\]|CRITICAL WARNING:", line, re.IGNORECASE):
            line_clean = line.strip()
            if line_clean and line_clean not in critical_warnings:
                critical_warnings.append(line_clean)
        
        # Extract regular warnings
        elif re.search(r"\[WARNING\]|WARNING:", line, re.IGNORECASE):
            line_clean = line.strip()
            if line_clean and line_clean not in warnings:
                warnings.append(line_clean)
    
    return errors, critical_warnings, warnings, synth_ok, impl_ok, bitstream_ok


# ============================================================================
# REPORT GENERATION
# ============================================================================

def analyze_design_reports(folder: Path) -> Dict[str, List[str]]:
    """Analyze design reports to detect async operations, clock issues, and FSM."""
    analysis = {"async": [], "clock": [], "fsm": [], "timing": []}
    
    # Analyze both report files and synthesis logs
    files_to_scan = list(folder.rglob("*.rpt")) + list(folder.rglob("*.log"))

    for rpt in files_to_scan:
        try:
            txt = rpt.read_text(errors="ignore")
            
            # Parse "Summary of Registers by Type" table for async set/reset
            # Look for rows where Total > 0 AND Asynchronous column has "Set" or "Reset"
            if "Summary of Registers by Type" in txt:
                lines = txt.split('\n')
                for i, line in enumerate(lines):
                    # Look for table data rows (start with |, not header)
                    if line.strip().startswith('|') and '+' not in line and 'Total' not in line:
                        parts = [p.strip() for p in line.split('|')[1:-1]]
                        if len(parts) >= 4:
                            try:
                                total = int(parts[0])
                                async_col = parts[3]
                                
                                # Check if async column has Set or Reset with non-zero count
                                if total > 0 and async_col in ['Set', 'Reset']:
                                    async_type = f"async {async_col.lower()}"
                                    msg = f"[ERROR] {total} register(s) with {async_type} detected in {rpt.name}"
                                    if msg not in analysis["async"]:
                                        analysis["async"].append(msg)
                            except (ValueError, IndexError):
                                pass
            
            # Check for inferred latches in synthesis logs
            if re.search(r"inferring latch|LD\s*\|\s*\d+", txt, re.IGNORECASE):
                latch_matches = re.findall(r"inferring latch for variable\s+'([^']+)'", txt, re.IGNORECASE)
                ld_matches = re.findall(r"LD\s*\|\s*(\d+)", txt)

                if latch_matches or ld_matches:
                    msg = f"[ERROR] Latches inferred in {rpt.name}"
                    if latch_matches:
                        msg += f": {', '.join(set(latch_matches[:3]))}"
                    if ld_matches:
                        ld_count = max(int(m) for m in ld_matches)
                        msg += f" ({ld_count} latch driver(s))"
                    if msg not in analysis["async"]:
                        analysis["async"].append(msg)

            # Quick check: detect explicit Global Id rows like '| g0 ...' to flag multiple global clocks
            try:
                # Do not flag io placement reports; they intentionally list many IO/global ids
                if not rpt.name.lower().endswith('_io_placed.rpt'):
                    g_matches = re.findall(r"^\|\s*(g\d+)\b", txt, re.IGNORECASE | re.MULTILINE)
                    if g_matches:
                        g_list = list(dict.fromkeys(g_matches))
                        if len(g_list) > 1:
                            msg = f"[ERROR] Multiple global clock IDs detected in {rpt.name}: {', '.join(g_list)}"
                            if msg not in analysis['clock']:
                                analysis['clock'].append(msg)
            except Exception:
                pass

            # Check for improper clock usage
            # Check for global clock sources table (detect multiple global clocks)
            # Look for common section headers used by Vivado reports
            # Match various Vivado headers for global clock tables (Resources/Source/Source Details)
            if re.search(r"Global Clock(?: Resources| Source Details| Source| Sources)?|Global Clocks", txt, re.IGNORECASE):
                # Scan subsequent lines for a pipe-delimited table of clock sources
                lines = txt.splitlines()
                for idx, l in enumerate(lines):
                    if re.search(r"Global Clock|Global clock|Global Clock Sources|Global Clocks", l, re.IGNORECASE):
                        # Collect following up-to-40 lines for table rows
                        clocks = []
                        for row in lines[idx+1: idx+41]:
                            if not row.strip():
                                break
                            if row.strip().startswith("|") and '+' not in row:
                                parts = [p.strip() for p in row.split('|')[1:-1]]
                                if not parts:
                                    continue
                                # Skip header-like rows
                                header_keywords = ('clock', 'name', 'source', 'type')
                                if any(k.lower() in parts[0].lower() for k in header_keywords) and any(k.lower() in '|'.join(parts).lower() for k in header_keywords):
                                    continue
                                # Use first column as clock name candidate
                                clock_name = parts[0]
                                if clock_name:
                                    clocks.append(clock_name)
                        # Remove empty and duplicate entries
                        clocks = [c for c in [c for c in clocks] if c]
                        clocks = list(dict.fromkeys(clocks))
                        # If more than one global clock source found, report as error
                        if len(clocks) > 1:
                            msg = f"[ERROR] Multiple global clock sources detected in {rpt.name}: {', '.join(clocks)}"
                            if msg not in analysis['clock']:
                                analysis['clock'].append(msg)
                        break

            # Fallback check for improper clock usage patterns
            if re.search(r"non.clock.*signal|non_clock|rising_edge.*non_clock|improper.*edge", txt, re.IGNORECASE):
                if rpt.name not in analysis["clock"]:
                    analysis["clock"].append(rpt.name)
            
            # Check for FSM patterns
            # Prefer specific synth inference lines from runme.log
            fsm_matches = re.findall(
                r"inferred FSM for state register\s+'([^']+)'\s+in module\s+'([^']+)'",
                txt,
                re.IGNORECASE,
            )
            for state_reg, module_name in fsm_matches:
                fsm_msg = (
                    f"[INFO] FSM inferred in {rpt.name}: "
                    f"module '{module_name}', state register '{state_reg}'"
                )
                if fsm_msg not in analysis["fsm"]:
                    analysis["fsm"].append(fsm_msg)

            # Generic fallback detection
            if re.search(r"\bfsm\b|finite.*state.*machine|state.*machine", txt, re.IGNORECASE):
                if not fsm_matches and rpt.name not in analysis["fsm"]:
                    analysis["fsm"].append(rpt.name)
        except Exception:
            pass
    
    return analysis


def extract_methodology_timing_violations(folder: Path) -> List[Dict[str, str]]:
    """Extract timing-rule summary rows from *_methodology_drc_routed.rpt files.

    Returns a list of dictionaries with keys:
    file, rule, severity, description, checks
    """
    rows: List[Dict[str, str]] = []

    for rpt in sorted(folder.rglob("*_methodology_drc_routed.rpt")):
        try:
            txt = rpt.read_text(errors="ignore")
        except Exception:
            continue

        # Matches summary table rows such as:
        # | TIMING-16 | Warning  | Large setup violation         | 640    |
        for match in re.finditer(
            r"^\|\s*(TIMING-\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*$",
            txt,
            re.MULTILINE,
        ):
            rule = match.group(1).strip()
            if rule == "TIMING-18":
                continue

            rows.append(
                {
                    "file": rpt.name,
                    "rule": rule,
                    "severity": match.group(2).strip(),
                    "description": match.group(3).strip(),
                    "checks": match.group(4).strip(),
                }
            )

    return rows


def write_report(folder: Path, xpr: Path, status: Tuple[bool, bool, bool], 
                 errors: List[str], crit: List[str], warns: List[str],
                 analysis: Dict[str, List[str]]) -> Path:
    """Generate comprehensive Markdown report with all results."""
    out = Path(folder) / "de1_grade_report.md"
    
    with open(out, "w", encoding="utf-8") as f:
        # Header
        f.write("# Vivado Project Report\n\n")
        
        # Project Info
        f.write("## [INFO] Project Info\n")
        f.write(f"- **Subgroup Path:** `{folder}`\n")
        f.write(f"- **Selected XPR:** `{xpr.name}`\n")
        f.write(f"- **Full Path:** `{xpr}`\n\n")
        
        # Build Status
        f.write("## [BUILD] Build Status\n")
        f.write(f"| Stage | Status |\n")
        f.write(f"|-------|--------|\n")
        f.write(f"| Synthesis | {'[OK] SUCCESS' if status[0] else '[FAIL] FAILED'} |\n")
        f.write(f"| Implementation | {'[OK] SUCCESS' if status[1] else '[FAIL] FAILED'} |\n")
        f.write(f"| Bitstream Generation | {'[OK] SUCCESS' if status[2] else '[FAIL] FAILED'} |\n")
        f.write("\n")
        
        # Errors
        if errors:
            f.write("## [ERROR] Errors\n")
            # Allow more errors to be reported in the Markdown (increase limit)
            for i, error in enumerate(errors[:200], 1):
                f.write(f"{i}. {error}\n")
            if len(errors) > 200:
                f.write(f"\n*... and {len(errors) - 200} more errors*\n")
            f.write("\n")
        else:
            f.write("## [ERROR] Errors\n")
            f.write("[OK] No errors detected\n\n")
        
        # Critical Warnings
        if crit:
            f.write("## [CRIT] Critical Warnings\n")
            for i, warning in enumerate(crit[:200], 1):
                f.write(f"{i}. {warning}\n")
            if len(crit) > 200:
                f.write(f"\n*... and {len(crit) - 200} more critical warnings*\n")
            f.write("\n")
        else:
            f.write("## [CRIT] Critical Warnings\n")
            f.write("[OK] No critical warnings detected\n\n")
        
        # Regular Warnings
        if warns:
            f.write("## [WARN] Warnings\n")
            f.write(f"**Total warnings:** {len(warns)}\n\n")
            for i, warning in enumerate(warns[:200], 1):
                f.write(f"{i}. {warning}\n")
            if len(warns) > 200:
                f.write(f"\n*... and {len(warns) - 200} more warnings*\n")
            f.write("\n")

        # Timing methodology summary
        f.write("## [TIMER] Timing Analysis\n\n")
        timing_rows = analysis.get("timing", [])
        if timing_rows:
            f.write("| Report | Rule | Severity | Description | Checks |\n")
            f.write("|--------|------|----------|-------------|--------|\n")
            for row in timing_rows:
                f.write(
                    f"| {row['file']} | {row['rule']} | {row['severity']} | {row['description']} | {row['checks']} |\n"
                )
            f.write("\n")
        else:
            f.write("[OK] No methodology timing-rule violations found (excluding TIMING-18)\n\n")
        
        # Design Analysis
        f.write("## [ANALYSIS] Design Analysis\n\n")
        
        # Async elements - mark as error if found
        f.write("### ASYNC Asynchronous Elements\n")
        if analysis.get("async", []):
            f.write(f"**[ERROR] Found {len(analysis['async'])} asynchronous element(s):**\n\n")
            for elem in analysis["async"]:
                f.write(f"- {elem}\n")
        else:
            f.write("[OK] No asynchronous elements detected\n")
        f.write("\n")
        
        # Improper clocks
        f.write("### CLOCK Improper Edge Usage\n")
        if analysis.get("clock", []):
            f.write(f"**Found {len(analysis['clock'])} potential issue(s):**\n\n")
            for clock in analysis["clock"]:
                f.write(f"- {clock}\n")
        else:
            f.write("[OK] No improper edge usage detected\n")
        f.write("\n")
        
        # FSM Detection
        f.write("### FSM Finite State Machine Detection\n")
        if analysis.get("fsm", []):
            f.write(f"**Finite State Machine Detected**\n\n")
            for item in analysis["fsm"]:
                f.write(f"- {item}\n")
        else:
            f.write("[OK] No FSM detected in design\n")
        f.write("\n")
        
        # Footer
        f.write("---\n")
        f.write("*Report generated by Vivado Batch Processor*\n")
    
    return out


# ============================================================================
# PROCESSING
# ============================================================================

def process_subgroup(folder: Path, args) -> bool:
    """Process a single subgroup folder."""
    try:
        print(f"  [SUBGROUP] {folder.name}")
        
        xprs = find_xpr_files(folder)
        
        if not xprs:
            print(f"    [INFO] No .xpr files found")
            return False
        
        print(f"    [INFO] Found {len(xprs)} project(s)")
        
        xpr = select_xpr(xprs, args)
        if not xpr:
            print(f"    [ERROR] No project selected")
            return False
        
        print(f"    [SELECT] {xpr.name}")
        
        # Generate Tcl script
        tcl = folder / "run_vivado_batch.tcl"
        generate_tcl_script(xpr, tcl, args.verbose)
        
        # Run Vivado
        print(f"    [RUN] Running Vivado...")
        output, returncode = run_vivado(args.vivado, tcl, folder, args.verbose)
        
        # Parse output
        errors, crit, warns, synth_ok, impl_ok, bitstream_ok = parse_vivado_output(output)
        status = (synth_ok, impl_ok, bitstream_ok)
        
        # Analyze design
        print(f"    [ANALYSIS] Analyzing reports...")
        analysis = analyze_design_reports(folder)
        analysis["timing"] = extract_methodology_timing_violations(folder)
        
        # Generate report
        report_path = write_report(folder, xpr, status, errors, crit, warns, analysis)
        print(f"    [REPORT] {report_path.name}")
        
        # Print summary
        status_str = f"Synth: {'[OK]' if status[0] else '[FAIL]'} | Impl: {'[OK]' if status[1] else '[FAIL]'} | Bitstream: {'[OK]' if status[2] else '[FAIL]'}"
        print(f"           {status_str}")
        
        # Cleanup
        if not args.keep_temp and tcl.exists():
            try:
                tcl.unlink()
            except:
                pass
        
        return True
        
    except Exception as e:
        print(f"    [ERROR] {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return False


# ============================================================================
# MAIN
# ============================================================================

def main():
    args = parse_args()
    
    root = Path(args.path) if args.path else Path.cwd()
    
    print("\n" + "="*70)
    print("[PROCESSOR] Xilinx Vivado 2025.2 - FPGA Project Batch Processor")
    print("="*70 + "\n")
    print(f"[INFO] Root: {root}\n")
    
    if not root.exists():
        print("[ERROR] Directory does not exist")
        return 1
    
    total_processed = 0
    total_successful = 0
    
    for group in sorted(root.iterdir()):
        if not group.is_dir():
            continue
        
        if args.group and args.group.lower() not in group.name.lower():
            continue
        
        print(f"[GROUP] {group.name}")
        
        subgroups_in_group = 0
        
        for subgroup in sorted(group.iterdir()):
            if not subgroup.is_dir():
                continue
            
            if args.subgroup and args.subgroup.lower() not in subgroup.name.lower():
                continue
            
            if process_subgroup(subgroup, args):
                total_successful += 1
            
            total_processed += 1
            subgroups_in_group += 1
        
        if subgroups_in_group > 0:
            print()
    
    # Summary
    print("="*70)
    print("[COMPLETE] Processing Complete")
    print(f"   Total subgroups: {total_processed}")
    print(f"   Successful: {total_successful}")
    print(f"   Failed: {total_processed - total_successful}")
    print("="*70 + "\n")
    
    return 0 if total_successful > 0 else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
