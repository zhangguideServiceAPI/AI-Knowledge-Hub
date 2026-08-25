"""受控字段映射和固定分支的纯计算，不访问数据库或执行 Node。"""

from collections.abc import Mapping

from app.workflow.definition import (
    WorkflowBranchDefinition,
    WorkflowInputBinding,
    WorkflowInputSource,
    WorkflowStepDefinition,
)
from app.workflow.exceptions import (
    WorkflowBranchResolutionError,
    WorkflowInputMappingError,
)


class WorkflowRouteResolver:
    """依据不可变 Definition 从安全 JSON 构造 Node 输入并选择固定后继。"""

    def build_node_input(
        self,
        step: WorkflowStepDefinition,
        *,
        run_input: Mapping[str, object],
        previous_step_output: Mapping[str, object] | None,
    ) -> dict[str, object]:
        """按 Step 的 bindings 复制字段；缺字段或无前序输出立即明确失败。"""

        node_input: dict[str, object] = {}
        for binding in step.input_bindings:
            source = self._source_for(binding, run_input, previous_step_output)
            try:
                node_input[binding.target_field] = source[binding.source_field]
            except KeyError as error:
                raise WorkflowInputMappingError(
                    f"Missing {binding.source.value} field: {binding.source_field}."
                ) from error
        return node_input

    def select_next_step_id(
        self,
        step: WorkflowStepDefinition,
        *,
        node_output: Mapping[str, object],
    ) -> str | None:
        """在线性后继或 selector 精确匹配的固定分支中选择唯一下一 Step。"""

        if step.branch is None:
            return step.next_step_id
        return self._select_branch_target(step.branch, node_output)

    @staticmethod
    def _source_for(
        binding: WorkflowInputBinding,
        run_input: Mapping[str, object],
        previous_step_output: Mapping[str, object] | None,
    ) -> Mapping[str, object]:
        """将声明来源映射到具体 JSON 对象，拒绝不存在的前序输出。"""

        if binding.source is WorkflowInputSource.RUN_INPUT:
            return run_input
        if previous_step_output is None:
            raise WorkflowInputMappingError(
                "previous_step_output is required by an input binding."
            )
        return previous_step_output

    @staticmethod
    def _select_branch_target(
        branch: WorkflowBranchDefinition,
        node_output: Mapping[str, object],
    ) -> str:
        """将 selector 字段的字符串值匹配到唯一 case，未知值绝不默认放行。"""

        try:
            selector_value = node_output[branch.selector_field]
        except KeyError as error:
            raise WorkflowBranchResolutionError(
                f"Missing branch selector field: {branch.selector_field}."
            ) from error
        if not isinstance(selector_value, str):
            raise WorkflowBranchResolutionError(
                f"Branch selector {branch.selector_field} must be a string."
            )
        for case in branch.cases:
            if case.expected_value == selector_value:
                return case.next_step_id
        raise WorkflowBranchResolutionError(
            f"Unsupported branch value for {branch.selector_field}: {selector_value}."
        )
