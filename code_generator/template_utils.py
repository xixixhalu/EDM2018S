import re
import json

TEMPLATE_PREFIX = "$"
TEMPLATE_FUNC_MARK = "\$FUNC"
TEMPLATE_FUNC_END_MARK = "\$ENDFUNC"

TEMPLATE_LANGUAGES = ["JavaScript", "Java", "Swift"]

TEMPLATE_PATH = {"Java": "code_templates/java/",
                 "JavaScript": "code_templates/javascript/",
                 "Swift": "code_templates/swift/"}
LANGUAGE_SUFFIX = {"Java": ".java",
                   "JavaScript": ".js",
                   "Swift": ".swift"}
LANGUAGE_CALLFORM = {"Java": "%s.%s(%s);",
                     "JavaScript": "%s.%s(%s, success(function), error(function))",
                     "Swift": "%s.%s(%s)"}

# not used yet
JAVA_TYPE_MAP = {"Integer": "int"}
JAVASCRIPT_TYPE_MAP = {}
LANGUAGE_TYPE_MAP = {"Java": JAVA_TYPE_MAP,
                     "JavaScript": JAVASCRIPT_TYPE_MAP}


def template_output_path(dm_name, language, username="default"):
    return "generated_code/%s/%s/%s/" % (username, dm_name, language)


def get_example_callform(example, language, model_name, method_name):
    if isinstance(example, list) and len(example) > 0:
        example_str = ""
        for sub_example in example:
            example_str += sub_example + ", "
        example = example_str[:-2]

    return (LANGUAGE_CALLFORM[language] % (model_name, method_name, example)).encode("utf-8")


# XXX need simplify
def get_examples(func_name, attribute_list):
    if len(attribute_list) == 0:
        return []
    examples = []
    attr1_name = attribute_list[0]["name"].encode("utf-8")
    attr1_type = attribute_list[0]["type"].encode("utf-8")
    if func_name == "create":
        example_one = {attr1_name: "some value (" + attr1_type + ")"}
        example_many = [{attr1_name: "some value (" + attr1_type + ")"},
                        {attr1_name: "some other value (" + attr1_type + ")"}]
        examples = [str(example_one), str(example_many)]
    elif func_name == "createOne":
        example_one = {attr1_name: "some value (" + attr1_type + ")"}
        examples = [str(example_one)]
    elif func_name == "createMany":
        example_many = [{attr1_name: "some value (" + attr1_type + ")"},
                        {attr1_name: "some other value (" + attr1_type + ")"}]
        examples = [str(example_many)]
    elif func_name == "read" or func_name == "readOne":
        example_id = {"_id": "specific id (String)"}
        example_attr = {attr1_name: "some value (" + attr1_type + ")"}
        examples = [str(example_id), str(example_attr)]
    elif func_name == "readMany":
        example_attr = {attr1_name: "some value (" + attr1_type + ")"}
        examples = [str(example_attr)]
    elif func_name == "update":
        '''example_update1 = {"oldData": {"_id": "specific id (String)"},
                           "newData": {attr1_name: "some value (" + attr1_type + ")"}}
        example_update2 = {"oldData": {attr1_name: "some value (" + attr1_type + ")"},
                           "newData": {attr1_name: "some other value (" + attr1_type + ")"}}'''

        example_update1 = ["{'_id': 'specific id (String)'}(search data)",
                           "{'%s': 'some value (%s)'}(update data)" % (attr1_name, attr1_type)]
        example_update2 = ["{'%s': 'some value (%s)'}(search data)" % (attr1_name, attr1_type),
                           "{'%s': 'some other value (%s)'}(update data)" % (attr1_name, attr1_type)]

        examples = [example_update1, example_update2]
    elif func_name == "delete":
        example_id = {"_id": "specific id (String)"}
        example_attr = {attr1_name: "some value (" + attr1_type + ")"}
        examples = [str(example_id), str(example_attr)]
    return examples

def remove_indent(func_str):
    func_strs = func_str.split("\n")
    indent = 100
    for line in func_strs:
        if len(line)==0:
            continue
        match_obj = re.match(" +", line)
        if not match_obj:
            return func_str
        if match_obj.span()[1] < indent:
            indent = match_obj.span()[1]

    for i in range(0, len(func_strs)):
        if len(func_strs[i])==0:
            continue
        func_strs[i] = func_strs[i][indent:]

    return "\n".join(func_strs)

def extract_funcs_info(template_content, language, model_name, attribute_list):
    pattern = TEMPLATE_FUNC_MARK + ''' (\S+)\s*\n(\{.*?\}\n)?(.*?)\n\s*''' + TEMPLATE_FUNC_END_MARK
    content = template_content
    func_info_list = []
    func_content_list = re.findall(pattern, content, re.S)
    for func_name, func_annotation, func_body in func_content_list:
        if len(func_annotation) > 2:
            func_annotation = func_annotation[1:-2]

        func_body = remove_indent(func_body)

        examples = get_examples(func_name, attribute_list)
        example_callforms = [get_example_callform(example, language, model_name, func_name)
                             for example in examples]

        func_info_list.append({"name": func_name,
                               "annotation": func_annotation,
                               "body": func_body,
                               "examples": example_callforms})
    content = re.sub(TEMPLATE_FUNC_MARK + " (\S+)\s*(\{.*?\})?", "", content, 0, re.S)
    content = re.sub(TEMPLATE_FUNC_END_MARK + "\s?", "", content)
    return content, func_info_list


def replace_strlist(template_content, keyword, name_list):
    list_str = json.dumps(name_list, ensure_ascii=False)
    list_str = list_str[1:-1]
    '''for name in name_list:
        #print name
        list_str += "\"" + name + "\", "
    list_str = list_str[:-2]'''
    content = template_content.replace(TEMPLATE_PREFIX + keyword, list_str)
    return content


def replace_words(template_content, replacements):
    content = template_content
    for key in replacements:
        replacement = replacements[key]
        content = content.replace(TEMPLATE_PREFIX + key, replacement)
    return content




# for test
'''def generate_template(ori_filename, simple_variables, replacements, output_filename):
    file_content = open(ori_filename, "r").read()
    for variable_name in simple_variables:
        file_content = file_content.replace(variable_name, TEMPLATE_PREFIX + variable_name)
    for ori_name in replacements:
        replacement = replacements[ori_name]
        file_content = file_content.replace(ori_name, replacement)
    output_file = open(output_filename, "w")
    output_file.write(file_content)
    output_file.close()'''

'''
def extract_model_data(json_data):
    model_data = {}
    for model_name in json_data:
        for element in json_data.get(model_name).get("elements"):
            elem_name = element.get("elementName")
            element_attrs = element.get("Attributes").get("Simple")
            attribute_list = [{"name": attribute["name"],
                               "type": attribute["details"]["type"]}
                              for attribute in element_attrs]
            model_data[elem_name] = attribute_list
        #for operation in json_data.get(model_name).get("Operations"):
            #operation_name = operation["name"]
    return model_data
'''