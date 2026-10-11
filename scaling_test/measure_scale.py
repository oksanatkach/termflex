"""Sequential vs parallel timing. Not a unit test: timings are too noisy for CI.

  python measure_scale.py                                  # synthetic corpus + CPU-burning fake checker
  python measure_scale.py --files 400 --units 100 --burn 50000 --workers 1,2,4,8
  python measure_scale.py --dir path/to/locale --tbx g.tbx --src en --tgt uk --workers 1,4 --format po   # real thing
"""
import argparse
import os
import tempfile
import time
from functools import partial

from tests.io.corpus import FIELD_OPTIONS, write_corpus
from tests.io.fake_checkers import make_slow_fake_checker
from termflex.io.io import collect_files, process_many


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", type=int, default=200)
    ap.add_argument("--units", type=int, default=50)
    ap.add_argument("--burn", type=int, default=20_000, help="fake CPU work per unit")
    ap.add_argument("--workers", default=f"1,2,4,{os.cpu_count()}")
    ap.add_argument("--repeat", type=int, default=2, help="runs per setting; best is reported")
    ap.add_argument("--format", action="append", choices=["po", "xliff", "csv", "json"],
                    dest="formats", help="formats to collect (default: all four)")
    ap.add_argument("--dir", help="use an existing directory instead of generating files")
    ap.add_argument("--tbx"); ap.add_argument("--src"); ap.add_argument("--tgt")
    ap.add_argument("--source-field"); ap.add_argument("--target-field")
    args = ap.parse_args()

    if args.tbx:
        from termflex.cli import make_checker
        factory = partial(make_checker, args.tbx, args.src, args.tgt)
    else:
        factory = partial(make_slow_fake_checker, args.burn)
    formats = args.formats or ["po", "xliff", "csv", "json"]
    options = ({"source_col": args.source_field, "target_col": args.target_field}
               if args.source_field else FIELD_OPTIONS)

    with tempfile.TemporaryDirectory() as tmp:
        root = args.dir or tmp
        if not args.dir:
            write_corpus(root, args.files, args.units)
        print(f"{len(collect_files(root, formats))} files, workers={args.workers}, cpus={os.cpu_count()}")

        reference, base = None, None
        for w in (int(x) for x in args.workers.split(",")):
            times = []
            for _ in range(args.repeat):
                t = time.perf_counter()
                results, errors = process_many(root, factory, options, max_workers=w, formats=formats)
                times.append(time.perf_counter() - t)
            reference = reference if reference is not None else results
            assert results == reference, f"workers={w} produced DIFFERENT results"
            best = min(times)
            base = base or best
            print(f"workers={w:>2}  {best:7.2f}s  speedup x{base / best:4.2f}  "
                  f"issues={sum(len(r['issues']) for r in results)}  errors={len(errors)}")


if __name__ == "__main__":      # required: worker processes re-import this module on macOS
    main()
