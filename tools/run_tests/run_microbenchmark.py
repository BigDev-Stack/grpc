#!/usr/bin/env python3
# Copyright 2017 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import html
import multiprocessing
import os
import subprocess
import sys

import python_utils.jobset as jobset
import python_utils.start_port_server as start_port_server

sys.path.append(
    os.path.join(os.path.dirname(sys.argv[0]), '..', 'profiling',
                 'microbenchmarks', 'bm_diff'))
import bm_constants

flamegraph_dir = os.path.join(os.path.expanduser('~'), 'FlameGraph')

os.chdir(os.path.join(os.path.dirname(sys.argv[0]), '../..'))
if not os.path.exists('reports'):
    os.makedirs('reports')

start_port_server.start_port_server()


def fnize(s):
    out = ''
    for c in s:
        if c in '<>, /':
            if len(out) and out[-1] == '_':
                continue
            out += '_'
        else:
            out += c
    return out


# index html
index_html = """
<html>
<head>
<title>Microbenchmark Results</title>
</head>
<body>
"""


def heading(name):
    global index_html
    index_html += "<h1>%s</h1>\n" % name


def link(txt, tgt):
    global index_html
    index_html += "<p><a href=\"%s\">%s</a></p>\n" % (html.escape(
        tgt, quote=True), html.escape(txt))


def text(txt):
    global index_html
    index_html += "<p><pre>%s</pre></p>\n" % html.escape(txt)


def _bazel_build_benchmark(bm_name, cfg):
    """Build given benchmark with bazel"""
    subprocess.check_call([
        'tools/bazel', 'build',
        '--config=%s' % cfg,
        '//test/cpp/microbenchmarks:%s' % bm_name
    ])


def collect_latency(bm_name, args):
    """generate latency profiles"""
    benchmarks = []
    profile_analysis = []
    cleanup = []

    heading('Latency Profiles: %s' % bm_name)
    _bazel_build_benchmark(bm_name, 'basicprof')
    for line in subprocess.check_output([
            'bazel-bin/test/cpp/microbenchmarks/%s' % bm_name,
            '--benchmark_list_tests'
    ]).decode('UTF-8').splitlines():
        link(line, '%s.txt' % fnize(line))
        benchmarks.append(
            jobset.JobSpec([
                'bazel-bin/test/cpp/microbenchmarks/%s' % bm_name,
                '--benchmark_filter=^%s$' % line, '--benchmark_min_time=0.05'
            ],
                           environ={
                               'GRPC_LATENCY_TRACE': '%s.trace' % fnize(line)
                           },
                           shortname='profile-%s' % fnize(line)))
        profile_analysis.append(
            jobset.JobSpec([
                sys.executable,
                'tools/profiling/latency_profile/profile_analyzer.py',
                '--source',
                '%s.trace' % fnize(line), '--fmt', 'simple', '--out',
                'reports/%s.txt' % fnize(line)
            ],
                           timeout_seconds=20 * 60,
                           shortname='analyze-%s' % fnize(line)))
        cleanup.append(jobset.JobSpec(['rm', '%s.trace' % fnize(line)]))
        # periodically flush out the list of jobs: profile_analysis jobs at least
        # consume upwards of five gigabytes of ram in some cases, and so analysing
        # hundreds of them at once is impractical -- but we want at least some
        # concurrency or the work takes too long
        if len(benchmarks) >= min(16, multiprocessing.cpu_count()):
            # run up to half the cpu count: each benchmark can use up to two cores
            # (one for the microbenchmark, one for the data flush)
            jobset.run(benchmarks,
                       maxjobs=max(1,
                                   multiprocessing.cpu_count() / 2))
            jobset.run(profile_analysis, maxjobs=multiprocessing.cpu_count())
            jobset.run(cleanup, maxjobs=multiprocessing.cpu_count())
            benchmarks = []
            profile_analysis = []
            cleanup = []
    # run the remaining benchmarks that weren't flushed
    if len(benchmarks):
        jobset.run(benchmarks, maxjobs=max(1, multiprocessing.cpu_count() / 2))
        jobset.run(profile_analysis, maxjobs=multiprocessing.cpu_count())
        jobset.run(cleanup, maxjobs=multiprocessing.cpu_count())


def collect_perf(bm_name, args):
    """generate flamegraphs"""
    heading('Flamegraphs: %s' % bm_name)
    _bazel_build_benchmark(bm_name, 'mutrace')
    benchmarks = []
    profile_analysis = []
    cleanup = []
    for line in subprocess.check_output([
            'bazel-bin/test/cpp/microbenchmarks/%s' % bm_name,
            '--benchmark_list_tests'
    ]).decode('UTF-8').splitlines():
        link(line, '%s.svg' % fnize(line))
        benchmarks.append(
            jobset.JobSpec([
                'perf', 'record', '-o',
                '%s-perf.data' % fnize(line), '-g', '-F', '997',
                'bazel-bin/test/cpp/microbenchmarks/%s' % bm_name,
                '--benchmark_filter=^%s$' % line, '--benchmark_min_time=10'
            ],
                           shortname='perf-%s' % fnize(line)))
        profile_analysis.append(
            jobset.JobSpec(
                [
                    'tools/run_tests/performance/process_local_perf_flamegraphs.sh'
                ],
                environ={
                    'PERF_BASE_NAME': fnize(line),
                    'OUTPUT_DIR': 'reports',
                    'OUTPUT_FILENAME': fnize(line),
                },
                shortname='flame-%s' % fnize(line)))
        cleanup.append(jobset.JobSpec(['rm', '%s-perf.data' % fnize(line)]))
        cleanup.append(jobset.JobSpec(['rm', '%s-out.perf' % fnize(line)]))
        # periodically flush out the list of jobs: temporary space required for this
        # processing is large
        if len(benchmarks) >= 20:
            # run up to half the cpu count: each benchmark can use up to two cores
            # (one for the microbenchmark, one for the data flush)
            jobset.run(benchmarks, maxjobs=1)
            jobset.run(profile_analysis, maxjobs=multiprocessing.cpu_count())
            jobset.run(cleanup, maxjobs=multiprocessing.cpu_count())
            benchmarks = []
            profile_analysis = []
            cleanup = []
    # run the remaining benchmarks that weren't flushed
    if len(benchmarks):
        jobset.run(benchmarks, maxjobs=1)
        jobset.run(profile_analysis, maxjobs=multiprocessing.cpu_count())
        jobset.run(cleanup, maxjobs=multiprocessing.cpu_count())


def run_summary(bm_name, cfg, base_json_name):
    _bazel_build_benchmark(bm_name, cfg)
    cmd = [
        'bazel-bin/test/cpp/microbenchmarks/%s' % bm_name,
        '--benchmark_out=%s.%s.json' % (base_json_name, cfg),
        '--benchmark_out_format=json'
    ]
    if args.summary_time is not None:
        cmd += ['--benchmark_min_time=%d' % args.summary_time]
    return subprocess.check_output(cmd).decode('UTF-8')


def collect_summary(bm_name, args):
    # no counters, run microbenchmark and add summary
    # both to HTML report and to console.
    nocounters_heading = 'Summary: %s [no counters]' % bm_name
    nocounters_summary = run_summary(bm_name, 'opt', bm_name)
    heading(nocounters_heading)
    text(nocounters_summary)
    print(nocounters_heading)
    print(nocounters_summary)

    # with counters, run microbenchmark and add summary
    # both to HTML report and to console.
    counters_heading = 'Summary: %s [with counters]' % bm_name
    counters_summary = run_summary(bm_name, 'counters', bm_name)
    heading(counters_heading)
    text(counters_summary)
    print(counters_heading)
    print(counters_summary)

    if args.bq_result_table:
        with open('%s.csv' % bm_name, 'w') as f:
            f.write(
                subprocess.check_output([
                    'tools/profiling/microbenchmarks/bm2bq.py',
                    '%s.counters.json' % bm_name,
                    '%s.opt.json' % bm_name
                ]).decode('UTF-8'))
        subprocess.check_call(
            ['bq', 'load',
             '%s' % args.bq_result_table,
             '%s.csv' % bm_name])


collectors = {
    'latency': collect_latency,
    'perf': collect_perf,
    'summary': collect_summary,
}

argp = argparse.ArgumentParser(description='Collect data from microbenchmarks')
argp.add_argument('-c',
                  '--collect',
                  choices=sorted(collectors.keys()),
                  nargs='*',
                  default=sorted(collectors.keys()),
                  help='Which collectors should be run against each benchmark')
argp.add_argument('-b',
                  '--benchmarks',
                  choices=bm_constants._AVAILABLE_BENCHMARK_TESTS,
                  default=bm_constants._AVAILABLE_BENCHMARK_TESTS,
                  nargs='+',
                  type=str,
                  help='Which microbenchmarks should be run')
argp.add_argument(
    '--bq_result_table',
    default='',
    type=str,
    help='Upload results from summary collection to a specified bigquery table.'
)
argp.add_argument(
    '--summary_time',
    default=None,
    type=int,
    help='Minimum time to run benchmarks for the summary collection')
args = argp.parse_args()

try:
    for collect in args.collect:
        for bm_name in args.benchmarks:
            collectors[collect](bm_name, args)
finally:
    if not os.path.exists('reports'):
        os.makedirs('reports')
    index_html += "</body>\n</html>\n"
    with open('reports/index.html', 'w') as f:
        f.write(index_html)
