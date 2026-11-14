from __future__ import annotations


REPORTED_FIELDS = ("name", "if", "continue-on-error", "uses")


def step_text(step, field):
    value = step.get(field)
    if isinstance(value, str) and value.strip():
        return value
    return None


def literal_action(step):
    if step_text(step, "name") is not None:
        return None

    action = step_text(step, "uses")
    if action is None or "${{" in action:
        return None
    if action.startswith(("./", "docker://")):
        return action

    action_path, separator, version = action.partition("@")
    if separator and version:
        return action_path
    return action


def identity_without_label(step):
    identity = {}
    for field, value in step.items():
        if field != "name" and field != "id":
            identity[field] = value
    identity.setdefault("continue-on-error", False)
    return identity


def unnamed_command(step):
    if step_text(step, "name") is not None:
        return None
    return step_text(step, "run")


def collect_step_keys(steps, key_function):
    keys = []
    for step in steps:
        keys.append(key_function(step))
    return keys


def collect_ids(steps):
    ids = []
    positions = {}
    invalid_positions = set()
    for index, step in enumerate(steps):
        identifier = step_text(step, "id")
        if identifier is not None:
            identifier = identifier.casefold()
            positions.setdefault(identifier, []).append(index)
        elif "id" in step:
            invalid_positions.add(index)
        ids.append(identifier)
    return ids, positions, invalid_positions


def compatible_ids(before_id, after_id):
    return before_id is None or after_id is None or before_id == after_id


def pair_by_key(
    before_keys,
    after_keys,
    before_ids,
    after_ids,
    blocked_before,
    blocked_after,
    pairs,
    paired_after,
):
    before_candidates = {}
    after_candidates = {}
    for before_index, before_key in enumerate(before_keys):
        if before_key is None:
            continue
        if before_index in blocked_before or before_index in pairs:
            continue

        for after_index, after_key in enumerate(after_keys):
            if after_index in blocked_after or after_index in paired_after:
                continue
            if before_key != after_key:
                continue
            if not compatible_ids(before_ids[before_index], after_ids[after_index]):
                continue

            before_candidates.setdefault(before_index, []).append(after_index)
            after_candidates.setdefault(after_index, []).append(before_index)

    for before_index, candidates in before_candidates.items():
        if len(candidates) == 1:
            after_index = candidates[0]
            if len(after_candidates[after_index]) == 1:
                pairs[before_index] = after_index
                paired_after.add(after_index)


def reordered_positions(pairs):
    positions = sorted(pairs)
    reordered = set()

    highest_after = -1
    for before_index in positions:
        after_index = pairs[before_index]
        if after_index < highest_after:
            reordered.add(before_index)
        highest_after = max(highest_after, after_index)

    lowest_after = float("inf")
    for before_index in reversed(positions):
        after_index = pairs[before_index]
        if after_index > lowest_after:
            reordered.add(before_index)
        lowest_after = min(lowest_after, after_index)

    return reordered


def field_value(step, field):
    if field == "continue-on-error":
        return step.get(field, False)
    return step.get(field)


def can_report_value(field, value):
    if value is None:
        return True
    if field == "continue-on-error" and isinstance(value, bool):
        return True
    if isinstance(value, str):
        if field == "uses":
            return "${{" not in value
        return True
    return False


def step_fields(before, after):
    fields = {}
    other_fields = set()
    for field in REPORTED_FIELDS:
        old_value = field_value(before, field)
        new_value = field_value(after, field)
        if type(old_value) is type(new_value) and old_value == new_value:
            continue

        if can_report_value(field, old_value) and can_report_value(field, new_value):
            fields[field] = {"before": old_value, "after": new_value}
        else:
            other_fields.add(field)

    available_fields = set(before)
    available_fields.update(after)
    for field in available_fields:
        if field in REPORTED_FIELDS:
            continue
        if field not in before or field not in after or before[field] != after[field]:
            other_fields.add(str(field))
    return fields, sorted(other_fields)


def step_label(step):
    name = step_text(step, "name")
    if name is not None:
        return name
    return step_text(step, "id")


def step_change(job, change, before_steps, after_steps, before_index, after_index):
    record = {
        "job": job,
        "change": change,
        "before_step": None,
        "after_step": None,
        "before_name": None,
        "after_name": None,
        "fields": {},
        "other_fields": [],
    }
    if before_index is not None:
        record["before_step"] = before_index + 1
        record["before_name"] = step_label(before_steps[before_index])
    if after_index is not None:
        record["after_step"] = after_index + 1
        record["after_name"] = step_label(after_steps[after_index])
    return record


def could_be_same_step(before, after):
    for field in ("name", "uses", "run"):
        old_value = step_text(before, field)
        if old_value is not None and old_value == step_text(after, field):
            return True

    if step_label(before) is None or step_label(after) is None:
        for field in ("run", "uses"):
            if field in before and field in after:
                return True

    return identity_without_label(before) == identity_without_label(after)


def pair_job_steps(before_steps, after_steps):
    before_ids, before_positions, blocked_before = collect_ids(before_steps)
    after_ids, after_positions, blocked_after = collect_ids(after_steps)
    identifiers = set(before_positions)
    identifiers.update(after_positions)
    pairs = {}
    paired_after = set()

    for identifier in identifiers:
        before_indices = before_positions.get(identifier, [])
        after_indices = after_positions.get(identifier, [])
        if len(before_indices) > 1 or len(after_indices) > 1:
            blocked_before.update(before_indices)
            blocked_after.update(after_indices)
        elif before_indices and after_indices:
            pairs[before_indices[0]] = after_indices[0]
            paired_after.add(after_indices[0])

    before_names = []
    for step in before_steps:
        before_names.append(step_text(step, "name"))
    after_names = []
    for step in after_steps:
        after_names.append(step_text(step, "name"))
    pair_by_key(
        before_names,
        after_names,
        before_ids,
        after_ids,
        blocked_before,
        blocked_after,
        pairs,
        paired_after,
    )

    before_identities = collect_step_keys(before_steps, identity_without_label)
    after_identities = collect_step_keys(after_steps, identity_without_label)
    pair_by_key(
        before_identities,
        after_identities,
        before_ids,
        after_ids,
        blocked_before,
        blocked_after,
        pairs,
        paired_after,
    )

    before_actions = collect_step_keys(before_steps, literal_action)
    after_actions = collect_step_keys(after_steps, literal_action)
    pair_by_key(
        before_actions,
        after_actions,
        before_ids,
        after_ids,
        blocked_before,
        blocked_after,
        pairs,
        paired_after,
    )

    before_commands = collect_step_keys(before_steps, unnamed_command)
    after_commands = collect_step_keys(after_steps, unnamed_command)
    pair_by_key(
        before_commands,
        after_commands,
        before_ids,
        after_ids,
        blocked_before,
        blocked_after,
        pairs,
        paired_after,
    )

    return {
        "pairs": pairs,
        "paired_after": paired_after,
        "before_ids": before_ids,
        "after_ids": after_ids,
        "blocked_before": blocked_before,
        "blocked_after": blocked_after,
    }


def compare_job_steps(job, before_steps, after_steps, *, sequential=True):
    if before_steps == after_steps:
        return []

    matching = pair_job_steps(before_steps, after_steps)
    pairs = matching["pairs"]
    paired_after = matching["paired_after"]
    before_ids = matching["before_ids"]
    after_ids = matching["after_ids"]
    blocked_before = matching["blocked_before"]
    blocked_after = matching["blocked_after"]
    ambiguous_before = set(blocked_before)
    ambiguous_after = set(blocked_after)
    for before_index, old_step in enumerate(before_steps):
        if before_index in pairs:
            continue
        for after_index, new_step in enumerate(after_steps):
            if after_index in paired_after:
                continue
            if compatible_ids(before_ids[before_index], after_ids[after_index]):
                if could_be_same_step(old_step, new_step):
                    ambiguous_before.add(before_index)
                    ambiguous_after.add(after_index)

    reordered = set()
    if sequential:
        reordered = reordered_positions(pairs)

    changes = []
    for before_index, old_step in enumerate(before_steps):
        if before_index not in pairs:
            change = "removed"
            if before_index in ambiguous_before:
                change = "unmatched"
            record = step_change(job, change, before_steps, after_steps, before_index, None)
            changes.append(record)
            continue

        after_index = pairs[before_index]
        fields, other_fields = step_fields(old_step, after_steps[after_index])
        if fields or other_fields:
            record = step_change(job, "modified", before_steps, after_steps, before_index, after_index)
            record["fields"] = fields
            record["other_fields"] = other_fields
            changes.append(record)
        if before_index in reordered:
            record = step_change(job, "reordered", before_steps, after_steps, before_index, after_index)
            changes.append(record)

    for after_index in range(len(after_steps)):
        if after_index not in paired_after:
            change = "added"
            if after_index in ambiguous_after:
                change = "unmatched"
            record = step_change(job, change, before_steps, after_steps, None, after_index)
            changes.append(record)
    return changes
