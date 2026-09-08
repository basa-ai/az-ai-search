from setup.create_datasource import create_datasource
from setup.create_index import create_index
from setup.create_indexer import create_indexer
from setup.create_skillset import create_skillset


def main() -> None:
    print("Creating search index...")
    create_index()

    print("Creating blob datasource...")
    create_datasource()

    print("Creating skillset...")
    create_skillset()

    print("Creating indexer...")
    create_indexer()

    print("Setup complete. Run 'python -m setup.run_indexer' to start indexing.")


if __name__ == "__main__":
    main()
