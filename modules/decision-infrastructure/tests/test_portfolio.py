from __future__ import annotations
import json
import unittest
from pathlib import Path
from delta_infra.portfolio import AlgorithmStrategy, CandidateMergeError, PortfolioController, PortfolioDefinitionError, StatePredicate, StateShape, StrategyCatalog, StrategyTurn, merge_candidate_outputs
from delta_infra.portfolio_cli import build_explicit_optimization_portfolio
from delta_infra.workflow import WorkflowRunStore

ROOT=Path(__file__).resolve().parents[1]
INSTANCE_PATH=ROOT/"examples"/"explicit_even_instance.json"

def stepping_strategy(name,family,*,quota=1,when=(),priority=0):
    def step(state):
        n=int(state.get("counter",0))+1; nxt=dict(state); nxt["counter"]=n
        nxt["log"]=[*state.get("log",[]),name]; nxt["done"]=n>=state.get("limit",99)
        return StrategyTurn("progress",nxt,metrics={"counter":n})
    return AlgorithmStrategy(name,family,step,tuple(when),priority=priority,turn_quota=quota)

class StateShapeTests(unittest.TestCase):
    def test_derives_basic_shape_signals(self):
        shape=StateShape.from_state({"kind":"matching","phase":"repair","selected":["a"],"target":["a","b","c"],
            "ground_set":["a","b","c"],"vertices":["a","b","c"],"edges":[["a","b"],["b","c"]],
            "matrix":[[0,1],[-1,0]],"objective_value":4.5,"features":{"mode":"explore"}})
        self.assertEqual(shape.kind,"matching"); self.assertEqual(shape.phase,"repair")
        self.assertEqual(shape.selected_parity,"odd"); self.assertEqual(shape.size,1); self.assertEqual(shape.ground_size,3)
        self.assertEqual(shape.distance,2); self.assertEqual(shape.objective,4.5); self.assertAlmostEqual(shape.density,2/3)
        self.assertEqual(shape.matrix_size,2); self.assertTrue(StatePredicate("features.mode","eq","explore").matches(shape))
    def test_rejects_bad_state_metadata(self):
        with self.assertRaises(PortfolioDefinitionError): StateShape.from_state({"stagnation":-1})
        with self.assertRaises(PortfolioDefinitionError): StateShape.from_state({"parity":"sometimes"})

class PortfolioSchedulingTests(unittest.TestCase):
    def run_with(self,strategies,*,mode,state=None,on_failure="stop",turns=20):
        catalog=StrategyCatalog()
        for strategy in strategies: catalog.register(strategy)
        initial={"counter":0,"log":[],"limit":turns,"done":False}
        if state: initial.update(state)
        return PortfolioController(catalog,on_failure=on_failure).run(initial,mode=mode,max_turns=turns)
    def test_rotation_takes_one_turn_per_eligible_strategy(self):
        result=self.run_with([stepping_strategy("alpha","one"),stepping_strategy("beta","two")],mode="rotation",turns=4)
        self.assertEqual(result["status"],"completed"); self.assertEqual(result["final_state"]["log"],["alpha","beta","alpha","beta"])
    def test_alternation_cycles_families_and_then_strategies_inside_family(self):
        result=self.run_with([stepping_strategy("left-1","left"),stepping_strategy("left-2","left"),stepping_strategy("right","right")],mode="alternation",turns=4)
        self.assertEqual(result["final_state"]["log"],["left-1","right","left-2","right"])
    def test_turn_taking_honors_weighted_quotas(self):
        result=self.run_with([stepping_strategy("heavy","a",quota=2),stepping_strategy("light","b",quota=1)],mode="turn-taking",turns=5)
        self.assertEqual(result["final_state"]["log"],["heavy","heavy","light","heavy","heavy"])
    def test_shape_driven_policy_switches_when_state_phase_changes(self):
        def explore(state):
            nxt=dict(state); nxt["phase"]="exploit"; nxt["done"]=False; nxt["log"]=[*state.get("log",[]),"explore"]; return StrategyTurn("progress",nxt)
        def exploit(state):
            nxt=dict(state); nxt["log"]=[*state.get("log",[]),"exploit"]; nxt["done"]=True; return StrategyTurn("complete",nxt)
        strategies=[AlgorithmStrategy("explore","search",explore,(StatePredicate("phase","eq","explore"),),priority=1),
                    AlgorithmStrategy("exploit","act",exploit,(StatePredicate("phase","eq","exploit"),),priority=99)]
        result=self.run_with(strategies,mode="shape-driven",state={"phase":"explore"},turns=5)
        self.assertEqual(result["status"],"completed"); self.assertEqual(result["final_state"]["log"],["explore","exploit"])
    def test_auto_mode_uses_state_selected_scheduler(self):
        result=self.run_with([stepping_strategy("a","A"),stepping_strategy("b","B")],mode="auto",state={"scheduler_mode":"alternation"},turns=4)
        self.assertEqual(result["mode_last_used"],"alternation"); self.assertEqual(result["final_state"]["log"],["a","b","a","b"])
    def test_ineligible_strategies_are_skipped_and_empty_eligibility_blocks(self):
        only_a=stepping_strategy("a","A",when=(StatePredicate("phase","eq","go"),))
        result=self.run_with([only_a],mode="rotation",state={"phase":"stop"},turns=4)
        self.assertEqual(result["status"],"blocked"); self.assertEqual(result["stop_reason"],"no_eligible_strategy_for_state_shape"); self.assertEqual(result["turn_count"],1)
    def test_preserved_key_violation_fails_closed(self):
        def corrupt(state):
            nxt=dict(state); nxt["problem_id"]="changed"; nxt["counter"]=1; return StrategyTurn("progress",nxt)
        result=self.run_with([AlgorithmStrategy("corruptor","bad",corrupt,preserve_keys=("problem_id",))],mode="rotation",state={"problem_id":"p"},turns=2)
        self.assertEqual(result["status"],"failed"); self.assertEqual(result["turns"][0]["status"],"contract_error"); self.assertIn("preserved state key",result["turns"][0]["error"])
    def test_progress_without_state_change_is_rejected(self):
        result=self.run_with([AlgorithmStrategy("lying","bad",lambda state:StrategyTurn("progress",dict(state)))],mode="rotation",turns=2)
        self.assertEqual(result["status"],"failed"); self.assertIn("without changing state",result["turns"][0]["error"])
    def test_skip_strategy_failure_policy_disables_failed_candidate(self):
        def fail(state): return StrategyTurn("failed",metrics={"code":"expected"},message="failed intentionally")
        result=self.run_with([AlgorithmStrategy("bad","a",fail),stepping_strategy("good","b")],mode="rotation",on_failure="skip_strategy",turns=2)
        self.assertEqual(result["final_state"]["log"],["good"]); self.assertEqual(result["disabled_strategies"],["bad"])
    def test_explicit_delta_matroid_portfolio_runs_algorithms_and_independent_verifier(self):
        instance=json.loads(INSTANCE_PATH.read_text(encoding="utf-8"))
        expected={"rotation":["local_search_primary","local_search_restart","signed_greedy","independent_verify"],
                  "alternation":["local_search_primary","signed_greedy","local_search_restart","independent_verify"]}
        for mode in ("rotation","alternation","turn-taking","shape-driven"):
            with self.subTest(mode=mode):
                controller,initial,catalog=build_explicit_optimization_portfolio(instance)
                result=controller.run(initial,mode=mode,max_turns=10)
                self.assertEqual(result["status"],"completed"); self.assertTrue(result["final_state"]["verification"]["verified"])
                self.assertEqual(result["final_state"]["verification"]["best_objective_value"],9)
                self.assertEqual(set(result["final_state"]["results"]),{"local_search_primary","local_search_restart","signed_greedy"})
                for row in result["final_state"]["results"].values(): self.assertEqual(row["objective_value"],9)
                if mode in expected: self.assertEqual([t["strategy"] for t in result["turns"]],expected[mode])
    def test_candidate_merge_chooses_best_feasible_and_reports_ties(self):
        merged=merge_candidate_outputs([{"name":"local","objective_value":6,"feasible":True},{"name":"greedy","objective_value":9,"feasible":True},{"name":"bad","objective_value":1000,"feasible":False},{"name":"restart","objective_value":9,"feasible":True}])
        self.assertEqual(merged["winner_name"],"greedy"); self.assertEqual(merged["objective_value"],9); self.assertEqual(merged["feasible_candidate_count"],3); self.assertEqual(merged["tie_count"],2)
        with self.assertRaises(CandidateMergeError): merge_candidate_outputs([{"name":"bad","objective_value":5,"feasible":False}])
    def test_feasibility_transition_contract_fails_closed(self):
        def make_infeasible(state):
            nxt=dict(state); nxt["counter"]=int(state.get("counter",0))+1; nxt["feasible"]=False; return StrategyTurn("progress",nxt)
        result=self.run_with([AlgorithmStrategy("break-feasibility","mutator",make_infeasible,require_after_feasible=True)],mode="rotation",state={"feasible":True},turns=2)
        self.assertEqual(result["status"],"failed"); self.assertIn("must preserve feasible=true",result["turns"][0]["error"])
    def test_auto_policy_can_change_from_ordered_state_shape_rules(self):
        def first_turn(state):
            nxt=dict(state); nxt["counter"]=int(state.get("counter",0))+1; nxt["log"]=[*state.get("log",[]),"a1"]; nxt["phase"]="steady"; nxt["done"]=False; return StrategyTurn("progress",nxt)
        strategies=[AlgorithmStrategy("a1","A",first_turn),stepping_strategy("a2","A"),stepping_strategy("b","B")]
        result=self.run_with(strategies,mode="auto",turns=4,state={"phase":"bootstrap","scheduler_rules":[
            {"name":"bootstrap-cycle","when":[{"field":"phase","op":"eq","value":"bootstrap"}],"mode":"rotation"},
            {"name":"steady-family-alternation","when":[{"field":"phase","op":"eq","value":"steady"}],"mode":"alternation"}]})
        self.assertEqual(result["status"],"completed"); self.assertEqual(result["turns"][0]["mode"],"rotation"); self.assertEqual(result["turns"][1]["mode"],"alternation"); self.assertEqual(result["final_state"]["log"][:3],["a1","b","a2"])
    def test_independent_verifier_falls_back_when_all_candidates_are_suboptimal(self):
        instance=json.loads(INSTANCE_PATH.read_text(encoding="utf-8")); _,state,catalog=build_explicit_optimization_portfolio(instance)
        state["phase"]="verify"; state["features"]["pending_solvers"]=[]; state["results"]={"bad-but-feasible":{"solution":["a","b"],"objective_value":2}}
        outcome=catalog.get("independent_verify").step(state)
        self.assertEqual(outcome.status,"complete"); self.assertTrue(outcome.next_state["verification"]["verified"]); self.assertFalse(outcome.next_state["verification"]["all_candidates_optimal"])
        self.assertTrue(outcome.next_state["portfolio_result"]["fallback_used"]); self.assertEqual(outcome.next_state["portfolio_result"]["solution"],["a","c"]); self.assertEqual(outcome.next_state["portfolio_result"]["objective_value"],9)
    def test_portfolio_run_can_share_the_sqlite_history_ledger(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            store=WorkflowRunStore(Path(temporary)/"runs.sqlite3"); catalog=StrategyCatalog(); catalog.register(stepping_strategy("only","demo"))
            result=PortfolioController(catalog,run_store=store).run({"counter":0,"limit":1,"log":[]},mode="rotation",max_turns=2)
            self.assertEqual(result["status"],"completed"); restored=store.get(result["run_id"]); self.assertEqual(restored["workflow_id"],"algorithm-portfolio")
            self.assertEqual(restored["final_state"]["log"],["only"]); self.assertEqual(store.list_runs(1)[0]["run_id"],result["run_id"])
    def test_cli_portfolio_accepts_shape_policy_rules_from_instance(self):
        instance=json.loads((ROOT/"examples"/"portfolio_adaptive_instance.json").read_text(encoding="utf-8"))
        controller,state,_=build_explicit_optimization_portfolio(instance); self.assertIn("scheduler_rules",state)
        result=controller.run(state,mode="auto",max_turns=10)
        self.assertEqual(result["status"],"completed"); self.assertEqual(result["turns"][0]["mode"],"alternation"); self.assertEqual(result["turns"][-1]["mode"],"shape-driven")
        self.assertEqual([t["strategy"] for t in result["turns"]],["local_search_primary","signed_greedy","local_search_restart","independent_verify"])
        self.assertTrue(result["final_state"]["verification"]["verified"])
    def test_auto_state_mode_and_unknown_mode_rejected(self):
        instance=json.loads(INSTANCE_PATH.read_text(encoding="utf-8")); controller,state,_=build_explicit_optimization_portfolio(instance)
        state["scheduler_mode"]="shape-driven"; self.assertEqual(controller.run(state,mode="auto")["status"],"completed")
        with self.assertRaises(PortfolioDefinitionError): controller.run(state,mode="teleport")


    def test_portfolio_checkpoints_and_resumes_only_retry_safe_strategies(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            store = WorkflowRunStore(Path(temporary) / "runs.sqlite3")
            catalog = StrategyCatalog()

            def increment(state):
                nxt = dict(state)
                nxt["counter"] = int(state.get("counter", 0)) + 1
                nxt["log"] = [*state.get("log", []), "increment"]
                nxt["done"] = nxt["counter"] >= state.get("limit", 99)
                return StrategyTurn("progress", nxt)

            catalog.register(AlgorithmStrategy(
                "increment", "deterministic", increment, retry_safe=True, version="test-1",
            ))
            controller = PortfolioController(catalog, run_store=store)
            initial = {"counter": 0, "limit": 99, "log": []}
            first = controller.run(initial, mode="rotation", max_turns=1)
            self.assertEqual(first["status"], "turn_limit_reached")
            run_id = first["run_id"]
            self.assertEqual(first["final_state"]["counter"], 1)
            checkpoint = store.get_latest_checkpoint(run_id)
            self.assertEqual(checkpoint["checkpoint"]["kind"], "portfolio-turn-checkpoint")
            self.assertEqual(checkpoint["checkpoint"]["next_turn_index"], 0)

            resumed = controller.run(
                initial, mode="rotation", max_turns=2, resume_from_run_id=run_id,
            )
            self.assertEqual(resumed["run_id"], run_id)
            self.assertEqual(resumed["status"], "turn_limit_reached")
            self.assertEqual(resumed["final_state"]["counter"], 2)
            self.assertEqual(resumed["final_state"]["log"], ["increment", "increment"])
            self.assertEqual(resumed["turn_count"], 2)
            self.assertGreaterEqual(len(store.list_checkpoints(run_id)), 3)

    def test_portfolio_resume_rejects_non_retry_safe_strategy(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            store = WorkflowRunStore(Path(temporary) / "runs.sqlite3")
            catalog = StrategyCatalog()
            catalog.register(stepping_strategy("not-safe", "demo"))
            controller = PortfolioController(catalog, run_store=store)
            with self.assertRaisesRegex(PortfolioDefinitionError, "retry_safe=true"):
                controller.run(
                    {"counter": 0, "limit": 99, "log": []},
                    mode="rotation", max_turns=2, resume_from_run_id="missing",
                )

    def test_portfolio_resume_rejects_changed_strategy_fingerprint(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            store = WorkflowRunStore(Path(temporary) / "runs.sqlite3")

            def increment(state):
                nxt = dict(state)
                nxt["counter"] = int(state.get("counter", 0)) + 1
                nxt["log"] = [*state.get("log", []), "increment"]
                nxt["done"] = False
                return StrategyTurn("progress", nxt)

            initial = {"counter": 0, "log": []}
            first_catalog = StrategyCatalog()
            first_catalog.register(AlgorithmStrategy(
                "increment", "deterministic", increment, retry_safe=True, version="test-1",
            ))
            first = PortfolioController(first_catalog, run_store=store).run(
                initial, mode="rotation", max_turns=1,
            )
            changed_catalog = StrategyCatalog()
            changed_catalog.register(AlgorithmStrategy(
                "increment", "deterministic", increment, retry_safe=True, version="test-2",
            ))
            with self.assertRaisesRegex(PortfolioDefinitionError, "differs from the checkpoint"):
                PortfolioController(changed_catalog, run_store=store).run(
                    initial, mode="rotation", max_turns=2, resume_from_run_id=first["run_id"],
                )


if __name__=="__main__": unittest.main()
