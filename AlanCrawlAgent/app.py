from datetime import datetime, timedelta
from est_alan_scheduler.task import Task
from est_alan_scheduler.task_registry import TaskRegistry, registry
from est_alan_scheduler.scheduler import start_scheduler


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] est-alan-crawl-agent 데모 시작...")

    # 예시 함수 정의
    def get_task_from_notion():
        list_task = list()
        return list_task

    def convert_notion_task_to_alan_task(notion_task: Task) -> Task:
        alan_task = Task()
        alan_task.task_id = notion_task.task_id
        alan_task.tags.append("notion_task")
        # do something
        # crawl and send
        return alan_task

    def sync_task_with_notion():
        list_task = get_task_from_notion()
        list_task_id = [task.id for task in list_task]

        for task in list_task:
            alan_task = convert_notion_task_to_alan_task(task)
            if alan_task.task_id in registry.store.keys():
                # 이미 등록된 task인 경우 update
                registry.update(alan_task)
            else:
                # 신규 task인 경우 register
                registry.register(alan_task)

        for task_id in registry.store.keys():
            if task_id not in list_task_id:
                registry.delete(task_id)

    task_notion = Task(
        at="07:00",
        func=sync_task_with_notion,
        args=(),
        id="task_update_notion_task",
        depends_on=[]
    )
    registry.register(task_notion)

    # 스케줄러 시작 (1초 간격, blocking 모드)
    start_scheduler(interval=1.0, blocking=True)


if __name__ == '__main__':
    main()
