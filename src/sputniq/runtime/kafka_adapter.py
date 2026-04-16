import os
import json
import uuid
import asyncio
from typing import Dict, Any, Callable
from langchain_core.tools import tool, StructuredTool

from sputniq.bus.kafka import KafkaMessageProducer, KafkaMessageConsumer
from sputniq.models.messages import ToolCommand, ToolResult

def create_kafka_langchain_tool(name: str, description: str, req_topic: str, res_topic: str, brokers: str):
    """
    Dynamically generates a LangChain tool that routes execution requests over Kafka
    while waiting for an asynchronous response. Keeps the platform abstracted from the dev.
    """
    producer = KafkaMessageProducer(bootstrap_servers=brokers)
    consumer = KafkaMessageConsumer(topics=[res_topic], bootstrap_servers=brokers, group_id=f"{name}-graph-group")

    async def kafka_rpc_call(endpoint: str, params: Dict[str, Any] = None) -> str:
        if getattr(producer, "_producer", None) is None:
            await producer.start()
            # Send a dummy message to ensure the topics exist before starting consumer
            try:
                await producer.publish(req_topic, ToolCommand(correlation_id="init", tool_id=name, endpoint="init", params={}))
                await producer.publish(res_topic, ToolResult(correlation_id="init", tool_id=name, status="success", result={}))
            except Exception:
                pass
            
            # Now we can safely start the consumer because the topic metadata exists
            import asyncio
            for _ in range(5):
                try:
                    await consumer.start()
                    break
                except Exception:
                    await asyncio.sleep(1)
            
        corr_id = str(uuid.uuid4())
        cmd = ToolCommand(
            correlation_id=corr_id,
            reply_to=res_topic,
            tool_id=name,
            endpoint=endpoint,
            params=params or {}
        )
        
        await producer.publish(req_topic, cmd)
        
        async for topic, msg in consumer.consume():
            if msg.get("correlation_id") == corr_id:
                result = ToolResult(**msg)
                if result.error_message:
                    raise RuntimeError(result.error_message)
                return json.dumps(result.result)

    # Return a LangChain compatible tool with dynamic signature mapping
    return StructuredTool.from_function(
        coroutine=kafka_rpc_call,
        name=name,
        description=description
    )

async def run_tool_worker(func: Callable, tool_id: str, req_topic: str, res_topic: str, brokers: str):
    """
    Centralized platform daemon that wraps any developer's Python function into a Kafka worker.
    """
    print(f"Platform: Starting Kafka Worker for tool '{tool_id}' on topic '{req_topic}'...")
    
    producer = KafkaMessageProducer(bootstrap_servers=brokers)
    consumer = KafkaMessageConsumer(topics=[req_topic], bootstrap_servers=brokers, group_id=f"{tool_id}-worker-group")
    
    await producer.start()
    
    # Send a dummy message to ensure topics exist and Auto-create kicks in
    try:
        await producer.publish(req_topic, ToolCommand(correlation_id="init", tool_id=tool_id, endpoint="init", params={}))
    except Exception:
        pass
        
    for _ in range(10):
        try:
            await consumer.start()
            break
        except Exception:
            await asyncio.sleep(1)
            
    try:
        async for topic, msg in consumer.consume():
            cmd = ToolCommand(**msg)
            if cmd.correlation_id == "init":
                continue
            try:
                # Execute pure developer abstraction
                import inspect
                if inspect.iscoroutinefunction(func):
                    result_data = await func(cmd.endpoint, cmd.params)
                else:
                    result_data = func(cmd.endpoint, cmd.params)
                status = "success"
                error_message = None
            except Exception as e:
                result_data = None
                status = "error"
                error_message = str(e)
                
            result = ToolResult(
                correlation_id=cmd.correlation_id,
                tool_id=cmd.tool_id,
                status=status,
                result=result_data,
                error_message=error_message
            )
            
            await producer.publish(cmd.reply_to or res_topic, result)
            
    finally:
        await producer.stop()
        await consumer.stop()

from sputniq.models.messages import AgentInput, AgentOutput

def create_kafka_agent_node(agent_id: str, req_topic: str, res_topic: str, brokers: str):
    """
    Dynamically generates a LangGraph compatible node function that routes execution 
    requests over Kafka while waiting for an asynchronous response. Keeps the platform 
    abstracted from the dev.
    """
    producer = KafkaMessageProducer(bootstrap_servers=brokers)
    consumer = KafkaMessageConsumer(topics=[res_topic], bootstrap_servers=brokers, group_id=f"{agent_id}-graph-group")

    async def kafka_rpc_node(state: Dict) -> Dict:
        if getattr(producer, "_producer", None) is None:
            await producer.start()
            # Send a dummy message to ensure topics exist
            try:
                await producer.publish(req_topic, AgentInput(correlation_id="init", agent_id=agent_id, payload={}))
                await producer.publish(res_topic, AgentOutput(correlation_id="init", agent_id=agent_id, result={}))
            except Exception:
                pass
            
            import asyncio
            for _ in range(5):
                try:
                    await consumer.start()
                    break
                except Exception:
                    await asyncio.sleep(1)
            
        corr_id = str(uuid.uuid4())
        
        # We need to serialize the state because it contains LangChain BaseMessage objects 
        # which aren't natively JSON serializable by standard json.dumps without help.
        # But LangChain provides a way to dump them
        from langchain_core.messages import message_to_dict, messages_from_dict
        
        serialized_state = {}
        for k, v in state.items():
            if k == "messages":
                serialized_state[k] = [message_to_dict(m) for m in v]
            else:
                serialized_state[k] = v

        cmd = AgentInput(
            correlation_id=corr_id,
            agent_id=agent_id,
            payload=serialized_state
        )
        
        await producer.publish(req_topic, cmd)
        
        async for topic, msg in consumer.consume():
            if msg.get("correlation_id") == corr_id:
                result = AgentOutput(**msg)
                
                if "error" in result.result:
                    raise RuntimeError(result.result["error"])
                
                # Deserialize the state
                deserialized_result = {}
                for k, v in result.result.items():
                    if k == "messages":
                        deserialized_result[k] = messages_from_dict(v)
                    else:
                        deserialized_result[k] = v
                return deserialized_result

    return kafka_rpc_node

async def run_agent_worker(agent_func: Callable, agent_id: str, req_topic: str, res_topic: str, brokers: str):
    """
    Centralized platform daemon that wraps any developer's LangGraph node into a Kafka worker.
    """
    print(f"Platform: Starting Kafka Worker for agent '{agent_id}' on topic '{req_topic}'...")
    
    producer = KafkaMessageProducer(bootstrap_servers=brokers)
    consumer = KafkaMessageConsumer(topics=[req_topic], bootstrap_servers=brokers, group_id=f"{agent_id}-worker-group")
    
    await producer.start()
    
    try:
        await producer.publish(req_topic, AgentInput(correlation_id="init", agent_id=agent_id, payload={}))
    except Exception:
        pass
        
    for _ in range(10):
        try:
            await consumer.start()
            break
        except Exception:
            await asyncio.sleep(1)
            
    try:
        from langchain_core.messages import messages_from_dict, message_to_dict
        async for topic, msg in consumer.consume():
            cmd = AgentInput(**msg)
            if cmd.correlation_id == "init":
                continue
            try:
                # Deserialize state
                state = {}
                for k, v in cmd.payload.items():
                    if k == "messages":
                        state[k] = messages_from_dict(v)
                    else:
                        state[k] = v

                # Execute pure developer abstraction
                import inspect
                if inspect.iscoroutinefunction(agent_func):
                    result_state = await agent_func(state)
                else:
                    result_state = agent_func(state)
                
                # Serialize state
                serialized_result = {}
                for k, v in result_state.items():
                    if k == "messages":
                        serialized_result[k] = [message_to_dict(m) for m in v]
                    else:
                        serialized_result[k] = v
                        
                result_data = serialized_result
            except Exception as e:
                import traceback
                traceback.print_exc()
                result_data = {"error": str(e)}
                
            result = AgentOutput(
                correlation_id=cmd.correlation_id,
                agent_id=cmd.agent_id,
                result=result_data
            )
            
            await producer.publish(res_topic, result)
            
    finally:
        await producer.stop()
        await consumer.stop()

