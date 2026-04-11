"""
main.py — CLI entry point for the MD-to-PPTX pipeline.

Usage:
    python main.py --input doc.md --master assets/slide_master.pptx [--output outputs/] [--slides 12] [--verbose] [--no-ai]
"""

import argparse
import json
import logging
import os
import sys

from dotenv import load_dotenv

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    SLIDE_COUNT_MIN,
    SLIDE_COUNT_MAX,
    SLIDE_COUNT_DEFAULT,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_MASTER_PATH,
    LOG_FORMAT,
    LOG_DATE_FORMAT,
)
from pipeline import MarkdownToPPTXPipeline

# Try rich for pretty output
try:
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.panel import Panel
    from rich import print as rprint
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


def main() -> None:
    """Main CLI entry point."""
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="md_to_pptx",
        description="Convert Markdown documents into polished PowerPoint presentations",
        epilog="Example: python main.py --input README.md --master assets/slide_master.pptx",
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to the input .md file",
    )
    parser.add_argument(
        "--master", "-m",
        required=True,
        help="Path to the slide_master.pptx template",
    )
    parser.add_argument(
        "--output", "-o",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--slides", "-s",
        type=int,
        default=SLIDE_COUNT_DEFAULT,
        help=f"Target slide count {SLIDE_COUNT_MIN}-{SLIDE_COUNT_MAX} (default: {SLIDE_COUNT_DEFAULT})",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable detailed logging",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Use rule-based fallback planner only (no AI API calls)",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
    )

    # Suppress noisy loggers
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Validate inputs
    if not os.path.isfile(args.input):
        _error(f"Input file not found: {args.input}")
        sys.exit(1)

    if not os.path.isfile(args.master):
        _error(f"Slide master not found: {args.master}")
        sys.exit(1)

    if not SLIDE_COUNT_MIN <= args.slides <= SLIDE_COUNT_MAX:
        _warn(f"Slide count {args.slides} outside [{SLIDE_COUNT_MIN}, {SLIDE_COUNT_MAX}], clamping")
        args.slides = max(SLIDE_COUNT_MIN, min(SLIDE_COUNT_MAX, args.slides))

    # Check for API key
    if not args.no_ai and not os.environ.get("ANTHROPIC_API_KEY"):
        _warn("ANTHROPIC_API_KEY not set — using rule-based fallback planner")
        args.no_ai = True

    # Print header
    _header(args)

    # Run pipeline
    pipeline = MarkdownToPPTXPipeline(
        master_path=args.master,
        output_dir=args.output,
        target_slides=args.slides,
        use_ai=not args.no_ai,
    )

    if HAS_RICH:
        console = Console()
        with Progress(
            SpinnerColumn("line"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Building presentation...", total=None)
            result = pipeline.run(args.input)
            progress.update(task, completed=True)
    else:
        print("\n⏳ Building presentation...")
        result = pipeline.run(args.input)

    # Print results
    _print_results(result)


def _header(args: argparse.Namespace) -> None:
    """Print the startup header.

    Args:
        args: Parsed CLI arguments.
    """
    if HAS_RICH:
        console = Console()
        console.print(Panel.fit(
            "[bold blue]EZ-Deck[/bold blue] - Markdown to PowerPoint Pipeline\n"
            f"[dim]Input:[/dim]  {args.input}\n"
            f"[dim]Master:[/dim] {args.master}\n"
            f"[dim]Target:[/dim] {args.slides} slides\n"
            f"[dim]Mode:[/dim]   {'Rule-based' if args.no_ai else 'AI-powered'}",
            title=">> MD to PPTX",
            border_style="blue",
        ))
    else:
        print("\n" + "=" * 50)
        print("  EZ-Deck — Markdown to PowerPoint Pipeline")
        print("=" * 50)
        print(f"  Input:  {args.input}")
        print(f"  Master: {args.master}")
        print(f"  Target: {args.slides} slides")
        print(f"  Mode:   {'Rule-based' if args.no_ai else 'AI-powered'}")
        print("=" * 50)


def _print_results(result: "PipelineResult") -> None:
    """Print the pipeline results.

    Args:
        result: PipelineResult from the pipeline.
    """
    if HAS_RICH:
        console = Console()
        console.print()

        # Results table
        table = Table(title="Pipeline Results", show_header=True)
        table.add_column("Metric", style="bold")
        table.add_column("Value")

        table.add_row("Output", result.output_path or "[red]None[/red]")
        table.add_row("Slides", str(result.slide_count))

        score = result.validation.score
        score_color = "green" if score >= 0.8 else "yellow" if score >= 0.6 else "red"
        table.add_row("Quality Score", f"[{score_color}]{score:.2%}[/{score_color}]")

        status = "[green]PASSED[/green]" if result.validation.passed else "[red]FAILED[/red]"
        table.add_row("Status", status)

        # Timing
        timing = result.timing
        if timing:
            table.add_row("Parse Time", f"{timing.get('parse_ms', 0)}ms")
            table.add_row("Plan Time", f"{timing.get('plan_ms', 0)}ms")
            table.add_row("Build Time", f"{timing.get('build_ms', 0)}ms")
            table.add_row("Total Time", f"{timing.get('total_ms', 0)}ms")

        console.print(table)

        # Warnings
        if result.warnings:
            console.print("\n[yellow]Warnings:[/yellow]")
            for w in result.warnings[:10]:
                console.print(f"  - {w}")

        # Errors
        if result.validation.errors:
            console.print("\n[red]Errors:[/red]")
            for e in result.validation.errors:
                console.print(f"  - {e}")

        console.print()

    else:
        print("\n" + "─" * 50)
        print("  PIPELINE RESULTS")
        print("─" * 50)
        print(f"  Output:  {result.output_path or 'None'}")
        print(f"  Slides:  {result.slide_count}")
        print(f"  Score:   {result.validation.score:.2%}")
        print(f"  Status:  {'PASSED' if result.validation.passed else 'FAILED'}")

        timing = result.timing
        if timing:
            print(f"  Parse:   {timing.get('parse_ms', 0)}ms")
            print(f"  Plan:    {timing.get('plan_ms', 0)}ms")
            print(f"  Build:   {timing.get('build_ms', 0)}ms")
            print(f"  Total:   {timing.get('total_ms', 0)}ms")

        if result.warnings:
            print("\n  Warnings:")
            for w in result.warnings[:10]:
                print(f"    • {w}")

        print("─" * 50 + "\n")


def _error(msg: str) -> None:
    """Print an error message.

    Args:
        msg: Error message.
    """
    if HAS_RICH:
        Console().print(f"[bold red]ERROR:[/bold red] {msg}")
    else:
        print(f"ERROR: {msg}", file=sys.stderr)


def _warn(msg: str) -> None:
    """Print a warning message.

    Args:
        msg: Warning message.
    """
    if HAS_RICH:
        Console().print(f"[yellow]WARNING:[/yellow] {msg}")
    else:
        print(f"WARNING: {msg}", file=sys.stderr)


if __name__ == "__main__":
    main()
