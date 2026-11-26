from .errors import Rejected
from .inputs import identifier, integer, labels


def matches(selector, tags):
    return all(tags.get(key) == value for key, value in selector.items())


def normalize_layers(value, validate_patch):
    if not isinstance(value, list) or len(value) > 64:
        raise Rejected("invalid_layers", "叠层最多 64 条，使用 JSON 数组")
    layers = []
    priorities = set()
    names = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"id", "priority", "when", "patch"}:
            raise Rejected("invalid_layer", "每个叠层应包含 id、priority、when、patch")
        name = identifier(item["id"], "叠层 ID")
        rank = integer(item["priority"], -10000, 10000, "叠层优先序")
        selector = labels(item["when"])
        if not selector:
            raise Rejected("empty_selector", "叠层至少需要一个标签条件")
        if rank in priorities or name in names:
            raise Rejected("duplicate_layer", "叠层 ID 和优先序均须唯一")
        priorities.add(rank)
        names.add(name)
        layers.append({"id": name, "priority": rank, "when": selector, "patch": validate_patch(item["patch"], patch=True)})
    return sorted(layers, key=lambda item: item["priority"])
