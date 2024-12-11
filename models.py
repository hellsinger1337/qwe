
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
import datetime

Base = declarative_base()

class Organization(Base):
    __tablename__ = 'organizations'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    activity = Column(String, nullable=False) 
    telegram_bot_token = Column(String, nullable=False)

    survey_day_of_week = Column(Integer)
    survey_hour = Column(Integer)
    survey_minute = Column(Integer)
    survey_frequency = Column(String, default='weekly') 

    report_day_of_week = Column(Integer)
    report_hour = Column(Integer)
    report_minute = Column(Integer)
    report_frequency = Column(String, default='weekly')

    employees = relationship("Employee", back_populates="organization")
    emails = relationship("Email", back_populates="organization", cascade="all, delete-orphan")
    messages = relationship("OrganizationMessage", back_populates="organization", cascade="all, delete-orphan", order_by="OrganizationMessage.order")

class Email(Base):
    __tablename__ = 'emails'
    id = Column(Integer, primary_key=True, index=True)
    email_address = Column(String, unique=True, nullable=False)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    organization = relationship("Organization", back_populates="emails")

class Employee(Base):
    __tablename__ = 'employees'
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True)
    name = Column(String, index=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'))
    organization = relationship("Organization", back_populates="employees")
    responses = relationship("Response", back_populates="employee")
    bot_messages = relationship("BotMessage", back_populates="employee", cascade="all, delete-orphan")

class Response(Base):
    __tablename__ = 'responses'
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey('employees.id'))
    response_text = Column(String)
    question = Column(String)  
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    employee = relationship("Employee", back_populates="responses")
    positive_points = relationship("PositivePoint", back_populates="response", cascade="all, delete-orphan")
    negative_points = relationship("NegativePoint", back_populates="response", cascade="all, delete-orphan")

class BotMessage(Base):
    __tablename__ = 'bot_messages'
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey('employees.id'))
    message_text = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    employee = relationship("Employee", back_populates="bot_messages")

class PositivePoint(Base):
    __tablename__ = 'positive_points'
    id = Column(Integer, primary_key=True, index=True)
    response_id = Column(Integer, ForeignKey('responses.id'))
    point_text = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)  
    response = relationship("Response", back_populates="positive_points")

class NegativePoint(Base):
    __tablename__ = 'negative_points'
    id = Column(Integer, primary_key=True, index=True)
    response_id = Column(Integer, ForeignKey('responses.id'))
    point_text = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)  
    response = relationship("Response", back_populates="negative_points")

class OrganizationMessage(Base):
    __tablename__ = 'organization_messages'
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    message_text = Column(String, nullable=False)
    order = Column(Integer, nullable=False)
    organization = relationship("Organization", back_populates="messages")