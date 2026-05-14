def fibonacci(n):
    """
    计算斐波那契数列的第n项（从0开始）
    
    斐波那契数列定义：
    F(0) = 0, F(1) = 1
    F(n) = F(n-1) + F(n-2)  (n >= 2)
    
    Args:
        n: 非负整数，表示要计算的项数
        
    Returns:
        第n个斐波那契数
        
    Raises:
        ValueError: 如果n为负数
    """
    if n < 0:
        raise ValueError("输入必须是非负整数")
    if n <= 1:
        return n
    
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b


def fibonacci_recursive(n):
    """
    递归方式计算斐波那契数列的第n项（不推荐，效率低）
    
    Args:
        n: 非负整数
        
    Returns:
        第n个斐波那契数
    """
    if n < 0:
        raise ValueError("输入必须是非负整数")
    if n <= 1:
        return n
    return fibonacci_recursive(n - 1) + fibonacci_recursive(n - 2)


def fibonacci_sequence(n):
    """
    生成斐波那契数列的前n项
    
    Args:
        n: 要生成的项数
        
    Returns:
        包含前n个斐波那契数的列表
    """
    if n <= 0:
        return []
    if n == 1:
        return [0]
    
    result = [0, 1]
    for i in range(2, n):
        result.append(result[i-1] + result[i-2])
    return result


# 使用示例
if __name__ == "__main__":
    print("=" * 50)
    print("斐波那契数列计算示例")
    print("=" * 50)
    
    # 计算第n项
    for i in range(10):
        print(f"F({i}) = {fibonacci(i)}")
    
    print("\n" + "=" * 50)
    print("前15项斐波那契数列:")
    print(fibonacci_sequence(15))
    
    print("\n" + "=" * 50)
    print("递归方式计算 F(10) =", fibonacci_recursive(10))
