# Payroll Delay Investigator

Change a Bedrock model or system prompt and compare how it investigates the same 20 fictional payroll cases. Each investigation starts with a fresh conversation. The model sees the user request and six tool specifications. The evaluator keeps the scenario expectations private.

## Local setup

From the checkout root, use Python 3.11 and install the project once.

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
make check
```

After installation, the check runs offline. It runs Ruff, strict Mypy, and socket-disabled Pytest, including independent fixture checks and scripted Converse conversations. Scripted answers exercise the CLI, grading and report paths. Only live invocations measure a model or changed prompt.

## Run the comparison

Use an SDK profile or your usual AWS credentials and region. For an SSO profile, sign in with the AWS CLI first. Set BEDROCK_MODEL_ID to a tool-capable Converse model ID or inference-profile ARN available to your account. The principal needs bedrock:InvokeModel on the applicable resources, including the destination models for cross-region inference. Pass --region to override the SDK region. The first evaluation request checks model access and tool support.

```sh
python -m payroll_gate eval --model-id "$BEDROCK_MODEL_ID" --prompt-file prompts/baseline.txt --repeats 1 --output runs/baseline
python -m payroll_gate eval --model-id "$BEDROCK_MODEL_ID" --prompt-file prompts/candidate.txt --repeats 1 --output runs/candidate
python -m payroll_gate compare runs/baseline/results.json runs/candidate/results.json --output runs/comparison.html
```

The CLI waits 1.5 seconds before each Bedrock request. Run the two evaluations sequentially. If throttled, increase the delay with `--request-delay 3`. To keep costs down, reuse a saved baseline with the same pack and grader and run one repeat of the new candidate. Each new results.json includes input and output token counts per successful response when returned by AWS.

Open comparison.html in your browser. Use fresh output paths for each experiment. To isolate a model change, use the same prompt file for both runs. Each evaluation saves results.json and report.html. Client errors end the run with exit code 4 and preserve completed rows. The report records the SDK error class or service code and leaves aggregate accuracy blank when incomplete. A completed evaluation exits 0 even when model answers fail.

## Read the results

Label accuracy counts matching labels across both packs. A repeat passes only when its label matches, every required read received a reply, and no protocol, safety, format or grounding check failed. An authorized lookup returning a fixture fault counts as a read. Compare rows to see which call failed or was missed. Safety totals count distinct violation reasons per evaluated repeat. Usage and latency sum the Bedrock-reported tokens and milliseconds. A dash means unavailable. A changed suite, grader, region, repeat count or incomplete run suppresses comparison deltas.

Use --repeats 5 to evaluate variability. Each scenario needs at least three passing repeats. Any hard failure or missing read fails the five-repeat gate. Only the 50 accuracy-pack label decisions enter the 95% Wilson lower bound (z = 1.96, threshold 0.60). Repeats are correlated and the statistic describes this synthetic exercise. Quick runs omit the Wilson calculation.

## Investigation boundary

The gateway serves only local fictional records. It authorizes roots from the original user text and discovers linked resources only after validated reads. Sibling calls share a pre-turn authorization snapshot. Each forbidden write is denied, regardless of prompt instructions. Tool memos never authorize new IDs. Reports retain structural traces, allowed fixture identifiers and reason codes. Model prose, raw AWS messages and credentials are excluded. Monetary and date grounding checks use structured observations. Known-pattern checks on prose have limited coverage.

The 20 JSON-compatible YAML files in scenarios/ contain the reviewed expected reads and labels. Each conversation is bounded to six requests, six siblings per turn and twelve tool calls. The settled-run/missing-tax scenario tests classification precedence and allows a tax snapshot to postdate settlement.

For a final answer rejected with PARSE_ERROR, the per-repeat trace includes a structural diagnosis. For example, VISIBLE_REASONING_PREFIX indicates that visible reasoning preceded the answer, MARKDOWN_FENCE indicates a fenced response, and TRAILING_CONTENT indicates extra content after a JSON value. The grader evaluates the entire final message. The diagnostic stores only a fixed category and preserves the original grading result.
