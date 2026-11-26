from . import contract, selectors


def normalize(base, layers):
    return contract.fields(base), selectors.normalize_layers(layers, contract.fields)


def resolve(base, layers, tags):
    value = base.copy()
    matched = []
    for layer in layers:
        if selectors.matches(layer["when"], tags):
            matched.append(layer["id"])
            for field, replacement in layer["patch"].items():
                if replacement is None:
                    value.pop(field, None)
                else:
                    value[field] = replacement
    contract.enforce(value)
    value.setdefault("compression", "off")
    return value, matched
