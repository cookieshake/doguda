from doguda import DogudaApp

app = DogudaApp("PriorityTest")

@app.provide(always=True, priority=10)
def high_priority():
    print("LOG: High priority (10) executing first")

@app.provide(always=True, priority=1)
def low_priority():
    print("LOG: Low priority (1) executing next")

@app.provide
def lazy_provider() -> str:
    print("LOG: Lazy provider executing only when needed")
    return "lazy_val"

@app.command
def my_cmd(val: str):
    print(f"LOG: Command executing with {val}")
    return {"status": "ok"}
