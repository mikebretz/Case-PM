// Copyright Sylvorin. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "SylvorinCharacter.generated.h"

UCLASS()
class SYLVORIN_API ASylvorinCharacter : public ACharacter
{
    GENERATED_BODY()

public:
    ASylvorinCharacter();

protected:
    virtual void SetupPlayerInputComponent(class UInputComponent* PlayerInputComponent) override;

    void MoveForward(float Value);
    void MoveRight(float Value);
};
