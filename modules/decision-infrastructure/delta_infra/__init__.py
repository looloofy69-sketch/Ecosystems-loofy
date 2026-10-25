"""Delta-Infrastructure Algorithm Workbench, version 0.8.0."""
from .algorithms import (
    local_search, signed_greedy, monotone_path, strong_path_explicit, strong_path_oracle,
    parity_correcting_lift, objective,
)
from .matrix import schur_path, PrimeField, RationalField
from .matching import MatchingDeltaMatroid, matching_separate, signed_greedy_matching_delta_matroid
from .oracles import ExplicitFamilyOracle, OracleContractError, TwistedSeparationOracle
from .registry import Capability, CapabilityRegistry, default_registry

__version__ = "0.8.0"

from .workflow import (
    TaskExecutionController, WorkflowDefinition, WorkflowRunStore,
    WorkflowDefinitionError, WorkflowInputError, verify_matching_optimum,
)

__all__ = [
    "local_search", "signed_greedy", "monotone_path", "strong_path_explicit", "strong_path_oracle",
    "parity_correcting_lift", "objective", "schur_path", "PrimeField", "RationalField",
    "MatchingDeltaMatroid", "matching_separate", "signed_greedy_matching_delta_matroid",
    "ExplicitFamilyOracle", "OracleContractError", "TwistedSeparationOracle",
    "Capability", "CapabilityRegistry", "default_registry",
    "TaskExecutionController", "WorkflowDefinition", "WorkflowRunStore",
    "WorkflowDefinitionError", "WorkflowInputError", "verify_matching_optimum",
]

from .portfolio import (
    AlgorithmStrategy, PortfolioController, PortfolioDefinitionError,
    StatePredicate, StateShape, StrategyCatalog, StrategyTurn, TransitionContractError,
    capability_strategy, merge_candidate_outputs, CandidateMergeError,
)

__all__ += [
    "AlgorithmStrategy", "PortfolioController", "PortfolioDefinitionError",
    "StatePredicate", "StateShape", "StrategyCatalog", "StrategyTurn",
    "TransitionContractError", "capability_strategy", "merge_candidate_outputs", "CandidateMergeError",
]

from .runtime import BudgetLedger, ExecutionBudget, ExecutionBudgetExceeded, ExecutionCancelled, RunContext, RuntimeGuard, RuntimePolicyError
__all__ += ["BudgetLedger", "ExecutionBudget", "ExecutionBudgetExceeded", "ExecutionCancelled", "RunContext", "RuntimeGuard", "RuntimePolicyError"]
