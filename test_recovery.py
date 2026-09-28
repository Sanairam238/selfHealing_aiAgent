from src.recovery.recovery_workflow import run_recovery_workflow

result = run_recovery_workflow(
    "workspace/student_task_manager",
    max_retries=1
)

print("\n========== FINAL RESULT ==========")
print(result)