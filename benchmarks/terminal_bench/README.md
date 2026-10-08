# Terminal-Bench / Harbor

This is an optional benchmark suite. Its Harbor and Terminal-Bench dependencies
are intentionally kept out of the OpenSpace runtime and default development
environment because their dependency ranges can differ from OpenSpace's pinned
runtime dependencies. Run it from a dedicated virtual environment.

Install `harbor`, `terminal-bench`, and the local OpenSpace checkout in that
environment, then validate the benchmark adapter configuration with:

```bash
python -m pytest -m terminal_bench tests/benchmarks/terminal_bench
```

Run Terminal-Bench 2.1 through Harbor:

```bash
python -m benchmarks.terminal_bench --sample sample20
```
