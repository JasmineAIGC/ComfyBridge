"""ComfyBridge 响应工具模块。

提供标准化的 API 响应构建函数，确保所有接口返回格式一致。

Functions:
    create_success_response: 构建成功响应
    create_error_response: 构建错误响应
"""

from typing import Dict, Any
from fastapi.responses import JSONResponse
from nexus.error_codes import SUCCESS, get_error_message


def create_success_response(data: Dict[str, Any]) -> JSONResponse:
    """构建标准成功响应。

    Args:
        data: 响应数据字典。

    Returns:
        JSONResponse: HTTP 200 响应，包含 status、errCode、errMsg、data 字段。
    """
    return JSONResponse(
        content={
            "status": "success",
            "errCode": SUCCESS,
            "errMsg": get_error_message(SUCCESS),
            "data": data
        },
        status_code=200
    )


def create_error_response(
    error_code: int,
    error_message: str = None,
    data: Dict[str, Any] = None,
    status_code: int = None
) -> JSONResponse:
    """构建标准错误响应。

    Args:
        error_code: 业务错误码。
        error_message: 错误描述，为 None 时自动从错误码映射获取。
        data: 附加数据，默认为空字典。
        status_code: HTTP 状态码，为 None 时根据错误码自动判断。

    Returns:
        JSONResponse: 包含 status、errCode、errMsg、data 字段的错误响应。
    """
    from nexus.error_codes import get_error_message, get_http_status_code

    if error_message is None:
        error_message = get_error_message(error_code)
    if data is None:
        data = {}
    if status_code is None:
        status_code = get_http_status_code(error_code)

    return JSONResponse(
        content={
            "status": "failure",
            "errCode": error_code,
            "errMsg": error_message,
            "data": data
        },
        status_code=status_code
    )
