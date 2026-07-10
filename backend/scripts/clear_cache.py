from app.infra.redis import ProjectCache


if __name__ == "__main__":
    deleted = ProjectCache().clear_project()
    print(f"Deleted {deleted} dawenzhang:* Redis keys from db1.")

