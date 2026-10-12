def infer_cuisine(name: str, category_name: str) -> str:
    text = category_name + name
    for word, cuisine in [
        ("火锅", "火锅"),
        ("烧烤", "烧烤"),
        ("面", "面馆"),
        ("轻食", "轻食"),
        ("沙拉", "轻食"),
        ("日本", "日韩料理"),
        ("韩国", "日韩料理"),
        ("泰国", "东南亚料理"),
        ("越南", "东南亚料理"),
        ("西餐", "西餐"),
        ("咖啡", "咖啡甜品"),
        ("甜品", "咖啡甜品"),
        ("快餐", "快餐"),
        ("小吃", "小吃"),
        ("中餐", "中餐"),
    ]:
        if word in text:
            return cuisine
    return "其他餐饮"
