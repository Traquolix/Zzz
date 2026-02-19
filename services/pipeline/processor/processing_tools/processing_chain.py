from typing import Any, Dict, List, Optional

from processor.processing_tools.processing_steps.base_step import ProcessingStep


class ProcessingChain:

    def __init__(self, steps: List[ProcessingStep]):
        self.steps = steps

    async def process(self, measurement_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        current_data = measurement_data
        for step in self.steps:
            if current_data is None:
                break
            current_data = await step.process_with_stats(current_data)
        return current_data

    def get_chain_stats(self) -> Dict[str, Any]:
        return {step.name: step.get_stats() for step in self.steps}

    def reset_all_stats(self):
        for step in self.steps:
            step.reset_stats()
