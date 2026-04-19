# Motivation
We want a system that is not only able to produce applications for prior authrization, but also be able to make appeals that have increasing likelyhood of successfully applying.

# Requirement
This feature will implement search and return the relevant learnings and inject this into the context of an LLM that is tasked with completing the prior authorization forms. The LLM recieves advice at all stages of the pipeline.
This feature is responsible for storing the memories to achieve this task.
Memories will be stored in a amazon database service.

## database structure
1. Must store a general knowedge.
2. Knowledge by provider.
3. Knowledge by treatment.
4. Knowledge by treatment, and provider.