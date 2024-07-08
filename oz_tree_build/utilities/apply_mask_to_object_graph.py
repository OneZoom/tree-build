# This is a marker object that is used to indicate that a property should be kept
KEEP = {}

# This is a marker key that states that we should apply the mask to all keys
ANY = "__ANY__"


def apply_mask_to_object_graph(
    obj,
    mask,
):
    """
    Takes an object and a mask and remove all the properties from the object
    that are not in the mask.
    """

    if mask is KEEP:
        return

    if type(obj) != type(mask):
        raise ValueError("Object and mask must be the same type")
    if isinstance(obj, dict):
        # Loop through all the keys in the object
        # We need to copy the keys into a list because we are going to be deleting some
        for key in list(obj.keys()):
            if ANY in mask:
                # The mask key is ANY, so apply mask to all actual keys
                apply_mask_to_object_graph(obj[key], mask[ANY])
            elif key in mask:
                # The key is in the mask, so apply recursively
                apply_mask_to_object_graph(obj[key], mask[key])
            else:
                # The key is not in the mask, so just remove it
                del obj[key]
    elif isinstance(obj, list):
        # The same list mask is used for all the items in the list
        if len(mask) != 1:
            raise ValueError("List mask must have exactly one element")

        # Loop through all the items in the list
        for element in obj:
            apply_mask_to_object_graph(element, mask[0])
    else:
        raise ValueError("Unexpected type")
