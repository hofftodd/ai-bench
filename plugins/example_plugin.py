"""Example plugin: every *.py in ./plugins is imported (see `plugins:` in bench.yaml).

Register a suite or backend with the decorators, then reference it by name as
`type:` in bench.yaml. This file is a working (if silly) suite; copy and edit.
"""

from aibench.backends.base import GenRequest
from aibench.registry import suite
from aibench.suites.base import RunContext, Suite, SuiteResult


@suite("example-arith")
class ArithSuite(Suite):
    description = "Example plugin: can the model add two numbers? (template for custom suites)"

    def __init__(self, key, pairs=((17, 25), (123, 877), (4096, 2048)), **options):
        super().__init__(key, **options)
        self.pairs = pairs

    async def run(self, ctx: RunContext) -> SuiteResult:
        res = SuiteResult()
        correct = 0
        for a, b in self.pairs:
            g = await ctx.backend.generate(ctx.model, GenRequest(
                messages=[{"role": "user", "content": f"What is {a} + {b}? Reply with just the number."}],
                max_tokens=ctx.model.max_tokens or 4096))
            ok = str(a + b) in g.text
            correct += ok
            res.samples.append({"a": a, "b": b, "response": g.text, "ok": ok})
        res.add("accuracy", 100 * correct / len(self.pairs), "%", headline=True)
        return res
